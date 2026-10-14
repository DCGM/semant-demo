import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Notify, QLayout, QPageContainer, Quasar } from 'quasar'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, effectScope, h } from 'vue'
import { createMemoryHistory, createRouter, RouterView, type RouteRecordRaw } from 'vue-router'

import { useUserStore } from 'src/features/auth/userStore'
import { useUserCollectionsStore } from 'src/features/user_collections/userCollectionsStore'
import { useSessionScope } from 'src/app/session'
import { installAuthGuard } from 'src/router/authGuard'
import { getAuthToken, setAuthToken, tokenSubject } from 'src/shared/api'
import MainLayout from 'src/app/MainLayout.vue'
import RagPage from 'src/features/rag/RagPage.vue'

// #267: session teardown on sign-out, expiry and account switch, also from another tab.

const userA = { id: 'uA', email: 'a@example.com', username: 'a', name: 'User A' }
const userB = { id: 'uB', email: 'b@example.com', username: 'b', name: 'User B' }
const Page = defineComponent({ render: () => h('div', 'page') })

// An unsigned JWT-shaped token for `sub` (the backend issues `sub` = user id).
function jwt (sub: string, nonce = '1'): string {
  const encode = (value: object) => btoa(JSON.stringify(value)).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_')
  return `${encode({ alg: 'HS256' })}.${encode({ sub, aud: ['fastapi-users:auth'], n: nonce })}.sig`
}

function stubNotify () {
  const original = Notify.create
  const create = vi.fn()
  Notify.create = create as unknown as typeof Notify.create
  return { create, messages: () => create.mock.calls.map(([options]) => options.message), restore: () => { Notify.create = original } }
}

/**
 * Another tab writes the shared token now; this tab hears of it (the storage event, a
 * separate task) only when `deliver` is called.
 */
function otherTabWrites (token: string | null) {
  if (token) localStorage.setItem('auth_token', token)
  else localStorage.removeItem('auth_token')
  return () => { window.dispatchEvent(new StorageEvent('storage', { key: 'auth_token', newValue: token, storageArea: localStorage })) }
}

/** What the browser does in this tab when another tab changes localStorage. */
function otherTabStores (token: string | null, key = 'auth_token', storageArea: Storage = localStorage) {
  if (key === 'auth_token' && storageArea === localStorage) {
    otherTabWrites(token)()
    return
  }
  window.dispatchEvent(new StorageEvent('storage', { key, newValue: token, storageArea }))
}

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/search' },
  { name: 'search', path: '/search', component: Page },
  { name: 'rag', path: '/rag', component: Page },
  { name: 'about', path: '/about', component: Page },
  { name: 'feedback', path: '/feedback', component: Page },
  {
    name: 'collections',
    path: '/collections',
    meta: { requiresAuth: true },
    component: RouterView,
    children: [{ name: 'collectionOverview', path: ':collectionId/overview', component: Page }]
  }
]

// Answers by request path; a path without an answer stays pending until `release`.
let answers: Record<string, () => Response | Promise<Response>>
let sent: Array<{ path: string, token: string | null }>
const originalFetch = globalThis.fetch

function json (body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  answers = {}
  sent = []
  globalThis.fetch = vi.fn((input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const path = new URL(url, 'http://localhost').pathname
    sent.push({ path, token: new Headers(init?.headers).get('Authorization')?.replace('Bearer ', '') ?? null })
    const answer = answers[path]
    return answer ? Promise.resolve(answer()) : new Promise<Response>(() => undefined)
  }) as typeof fetch
})

afterEach(() => {
  globalThis.fetch = originalFetch
  localStorage.clear()
})

describe('tokenSubject', () => {
  it('reads the user id of a JWT and nothing from other strings', () => {
    expect(tokenSubject(jwt('uA'))).toBe('uA')
    expect([tokenSubject('opaque'), tokenSubject('a.%%%.c'), tokenSubject('')]).toEqual([null, null, null])
  })
})

describe('session changes in another tab', () => {
  async function setup (path = '/collections/c1/overview') {
    const notify = stubNotify()
    const scope = effectScope()
    scope.run(useSessionScope)
    const store = useUserStore()
    const router = createRouter({ history: createMemoryHistory(), routes })
    installAuthGuard(router, store, () => undefined)
    setAuthToken(jwt('uA'))
    store.token = jwt('uA')
    store.user = userA as never
    const collections = useUserCollectionsStore()
    answers['/api/user_collections'] = () => json([{ id: 'c1', name: 'A private collection', userId: 'uA' }])
    await collections.fetchCollections()
    expect(collections.collections).toHaveLength(1)
    sent = []
    localStorage.setItem('collections.viewMode', 'grid')
    await router.push(path)
    return { notify, scope, store, router, collections }
  }

  let cleanup: Array<() => void> = []
  afterEach(() => {
    cleanup.forEach((fn) => fn())
    cleanup = []
  })

  it('a sign-out there clears this tab\'s data and leaves the protected route without a reload', async () => {
    const { notify, scope, store, router, collections } = await setup()
    cleanup.push(notify.restore, () => scope.stop())

    otherTabStores(null)
    await flushPromises()

    expect([store.isLoggedIn, store.token, store.user]).toEqual([false, null, null])
    expect(collections.collections).toEqual([])
    expect(router.currentRoute.value.name).toBe('search')
    expect(notify.messages()).toEqual(['You signed out in another tab.'])
    expect(localStorage.getItem('collections.viewMode')).toBe('grid') // preferences stay
  })

  it('an account switch there clears the old user\'s data before the new user is shown', async () => {
    const { notify, scope, store, router, collections } = await setup()
    cleanup.push(notify.restore, () => scope.stop())
    let answerB!: () => void
    answers['/api/users/me'] = () => new Promise((resolve) => { answerB = () => resolve(json(userB)) })

    otherTabStores(jwt('uB'))
    await flushPromises()

    // While B is being restored, nothing of A is shown and no protected page is open.
    expect([store.user, store.isLoggedIn]).toEqual([null, false])
    expect(collections.collections).toEqual([])
    expect(router.currentRoute.value.name).toBe('search')
    expect(sent).toEqual([{ path: '/api/users/me', token: jwt('uB') }])

    answerB()
    await flushPromises()
    expect([store.user?.id, store.token, getAuthToken()]).toEqual(['uB', jwt('uB'), jwt('uB')]) // B's token is not removed
    expect(notify.messages()).toEqual(['Your session changed in another tab.'])
  })

  it('a new token of the same user (renewed or signed in again) keeps the session and its data', async () => {
    const { notify, scope, store, router, collections } = await setup()
    cleanup.push(notify.restore, () => scope.stop())

    otherTabStores(jwt('uA', '2'))
    await flushPromises()

    expect([store.token, store.user?.id]).toEqual([jwt('uA', '2'), 'uA'])
    expect(collections.collections).toHaveLength(1)
    expect(router.currentRoute.value.name).toBe('collectionOverview')
    expect([sent, notify.messages()]).toEqual([[], []])
  })

  it('a token whose user cannot be read is treated as another account', async () => {
    const { notify, scope, store, collections } = await setup()
    cleanup.push(notify.restore, () => scope.stop())
    answers['/api/users/me'] = () => json(userA)

    otherTabStores('opaque-token')
    await flushPromises()

    expect(collections.collections).toEqual([])
    expect([store.token, store.user?.id]).toEqual(['opaque-token', 'uA'])
  })

  it('a sign-in there signs this signed-out tab in, without a notice', async () => {
    const notify = stubNotify()
    const scope = effectScope()
    scope.run(useSessionScope)
    cleanup.push(notify.restore, () => scope.stop())
    const store = useUserStore()
    answers['/api/users/me'] = () => json(userA)

    otherTabStores(jwt('uA'))
    await flushPromises()

    expect([store.isLoggedIn, store.user?.id]).toEqual([true, 'uA'])
    expect(notify.messages()).toEqual([])
  })

  it('ignores other keys, other storage areas and its own token', async () => {
    const { notify, scope, store, collections } = await setup()
    cleanup.push(notify.restore, () => scope.stop())

    otherTabStores('x', 'collections.viewMode')
    otherTabStores(null, 'auth_token', sessionStorage)
    window.dispatchEvent(new StorageEvent('storage', { key: 'auth_token', newValue: jwt('uA'), storageArea: localStorage }))
    await flushPromises()

    expect([store.isLoggedIn, store.user?.id]).toEqual([true, 'uA'])
    expect(collections.collections).toHaveLength(1)
    expect([sent, notify.messages()]).toEqual([[], []])
  })

  it('stops listening when the scope ends', async () => {
    const { notify, scope, store } = await setup()
    cleanup.push(notify.restore)
    scope.stop()

    otherTabStores(null)
    await flushPromises()

    expect(store.user?.id).toBe('uA')
  })
})

describe('late account answers', () => {
  it('a profile update answered after sign-out does not bring the old user back', async () => {
    const store = useUserStore()
    setAuthToken(jwt('uA'))
    store.token = jwt('uA')
    store.user = userA as never
    let answer!: () => void
    answers['/api/users/me'] = () => new Promise((resolve) => { answer = () => resolve(json({ ...userA, name: 'Renamed' })) })

    const update = store.updateUser({ name: 'Renamed' })
    await flushPromises()
    store.forgetSession()
    answer()
    await update

    expect([store.user, store.token, store.isLoggedIn]).toEqual([null, null, false])
  })
})

describe('a newer session stored by another tab', () => {
  // This tab is signed in as A; `useSessionScope` follows the other tab.
  function signedInAsA () {
    const notify = stubNotify()
    const scope = effectScope()
    scope.run(useSessionScope)
    const store = useUserStore()
    setAuthToken(jwt('uA'))
    store.token = jwt('uA')
    store.user = userA as never
    return { notify, scope, store, stop: () => { notify.restore(); scope.stop() } }
  }

  function holdLogout () {
    let release!: () => void
    answers['/api/auth/jwt/logout'] = () => new Promise((resolve) => { release = () => resolve(new Response(null, { status: 204 })) })
    return () => release()
  }

  it('survives a logout that was pending here, before this tab heard of it', async () => {
    const { store, stop } = signedInAsA()
    const releaseLogout = holdLogout()
    answers['/api/users/me'] = () => json(userB)

    const logout = store.logout()
    await flushPromises()
    const deliver = otherTabWrites(jwt('uB')) // the other tab signs in as B
    releaseLogout()
    await logout

    expect([store.token, getAuthToken()]).toEqual([null, jwt('uB')]) // A ended here, B's token kept
    deliver()
    await flushPromises()
    expect([store.user?.id, getAuthToken()]).toEqual(['uB', jwt('uB')])
    stop()
  })

  it('survives a logout that was pending here, after this tab followed it', async () => {
    const { store, stop } = signedInAsA()
    const releaseLogout = holdLogout()
    answers['/api/users/me'] = () => json(userB)

    const logout = store.logout()
    await flushPromises()
    otherTabStores(jwt('uB'))
    await flushPromises()
    releaseLogout()
    await logout

    expect([store.token, store.user?.id, getAuthToken()]).toEqual([jwt('uB'), 'uB', jwt('uB')])
    stop()
  })

  it('survives a 401 for the old token answered before this tab heard of it', async () => {
    const { store, stop } = signedInAsA()
    let reject!: () => void
    answers['/api/user_collections'] = () => new Promise((resolve) => { reject = () => resolve(json({ detail: 'Unauthorized' }, 401)) })
    answers['/api/users/me'] = () => json(userB)

    const listing = useUserCollectionsStore().fetchCollections() // sent with A's token
    await flushPromises()
    const deliver = otherTabWrites(jwt('uB'))
    reject() // A's token is rejected (expired) while B's is already stored
    await listing
    await flushPromises()

    expect(sent.find((r) => r.path === '/api/user_collections')?.token).toBe(jwt('uA'))
    expect([store.isLoggedIn, getAuthToken()]).toEqual([false, jwt('uB')])
    deliver()
    await flushPromises()
    expect([store.user?.id, getAuthToken()]).toEqual(['uB', jwt('uB')])
    stop()
  })
})

describe('MainLayout session teardown', () => {
  async function mountLayout () {
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createRouter({ history: createMemoryHistory(), routes })
    await router.push('/search')
    const wrapper = mount(MainLayout, {
      global: {
        plugins: [[Quasar, { plugins: { Notify } }], pinia, router],
        stubs: { RightSidebar: true, LoginDialog: true, RegisterDialog: true, UserInfoDialog: true, AboutAppDialog: true }
      }
    })
    await flushPromises()
    const store = useUserStore()
    setAuthToken(jwt('uA'))
    store.token = jwt('uA')
    store.user = userA as never
    await flushPromises()
    return { wrapper, store }
  }

  const drawerItem = (wrapper: Awaited<ReturnType<typeof mountLayout>>['wrapper'], label: string) =>
    wrapper.findAll('.drawer-item').find((item) => item.text().includes(label))

  it('signs out locally and says so accurately when the server logout fails', async () => {
    const { wrapper, store } = await mountLayout()
    localStorage.setItem('collections.viewMode', 'grid')
    answers['/api/auth/jwt/logout'] = () => { throw new TypeError('Failed to fetch') }

    await drawerItem(wrapper, 'Sign out')?.trigger('click')
    await flushPromises()

    expect([store.isLoggedIn, getAuthToken()]).toEqual([false, null])
    expect(document.body.textContent).toContain('You have been logged out on this device, but the server could not confirm the sign-out.')
    expect(localStorage.getItem('collections.viewMode')).toBe('grid')
  })

  it('reports a plain sign-out when the server answers it', async () => {
    const { wrapper, store } = await mountLayout()
    answers['/api/auth/jwt/logout'] = () => new Response(null, { status: 204 })

    await drawerItem(wrapper, 'Sign out')?.trigger('click')
    await flushPromises()

    expect(store.isLoggedIn).toBe(false)
    expect(sent.find((r) => r.path === '/api/auth/jwt/logout')?.token).toBe(jwt('uA'))
  })

  it('closes the open account dialog when the session ends or the account changes', async () => {
    const { wrapper, store } = await mountLayout()
    const accountDialog = () => wrapper.findComponent({ name: 'UserInfoDialog' })

    await drawerItem(wrapper, 'Settings')?.trigger('click')
    await flushPromises()
    expect(accountDialog().props('modelValue')).toBe(true)
    store.forgetSession()
    await flushPromises()
    expect(accountDialog().props('modelValue')).toBe(false)

    store.token = jwt('uA')
    store.user = userA as never
    await flushPromises()
    await drawerItem(wrapper, 'Settings')?.trigger('click')
    await flushPromises()
    store.token = jwt('uB')
    store.user = userB as never // switched without passing through signed-out
    await flushPromises()
    expect(accountDialog().props('modelValue')).toBe(false)
  })

  it('closes Log in when another tab signed in meanwhile', async () => {
    const { wrapper, store } = await mountLayout()
    store.forgetSession()
    await flushPromises()
    await drawerItem(wrapper, 'Log in')?.trigger('click')
    await flushPromises()
    expect(wrapper.findComponent({ name: 'LoginDialog' }).props('modelValue')).toBe(true)

    store.token = jwt('uA')
    store.user = userA as never
    await flushPromises()

    expect(wrapper.findComponent({ name: 'LoginDialog' }).props('modelValue')).toBe(false)
  })
})

describe('Chat Assistant on sign-out', () => {
  const source = { id: 'ch1', text: 'Source text of the old conversation', document: 'd1', document_object: { id: 'd1' } }

  async function mountRag (onError?: (err: unknown) => void) {
    answers['/api/rag/configurations'] = () => json([{ id: 'r1', name: 'RAG', description: '' }])
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useUserStore()
    setAuthToken(jwt('uA'))
    store.token = jwt('uA')
    store.user = userA as never
    const InLayout = defineComponent({ render: () => h(QLayout, () => h(QPageContainer, () => h(RagPage))) })
    const layout = mount(InLayout, {
      attachTo: document.body,
      global: { plugins: [[Quasar, { plugins: { Notify } }], pinia], config: onError ? { errorHandler: onError } : {} }
    })
    await flushPromises()
    return { wrapper: layout.findComponent(RagPage), store, unmount: () => layout.unmount() }
  }

  async function ask (wrapper: Awaited<ReturnType<typeof mountRag>>['wrapper'], question: string) {
    const input = wrapper.find('input[placeholder="Vaše otázka?"]')
    await input.setValue(question)
    await wrapper.findAll('button').find((b) => b.text() === 'send')?.trigger('click')
    await flushPromises()
  }

  it('drops the conversation and an answer still on its way', async () => {
    const { wrapper, store, unmount } = await mountRag()
    let answer!: () => void
    answers['/api/rag'] = () => new Promise((resolve) => {
      answer = () => resolve(json({ rag_answer: 'Private answer [doc 1]', sources: [source], response_id: 'x', time_spent: 1 }))
    })

    await ask(wrapper, 'My private question')
    expect(wrapper.text()).toContain('My private question')

    store.forgetSession()
    await flushPromises()
    answer()
    await flushPromises()

    expect(wrapper.text()).not.toContain('My private question')
    expect(wrapper.text()).not.toContain('Private answer')
    expect(wrapper.text()).toContain('Ahoj, máte na mě nějakou otázku?')
    unmount()
  })

  it('closes an open sources dialog of the old conversation', async () => {
    const { wrapper, store, unmount } = await mountRag()
    answers['/api/rag'] = () => json({ rag_answer: 'Answer', sources: [source], response_id: 'x', time_spent: 1 })
    await ask(wrapper, 'Question')
    await wrapper.find('a.source-link').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain(source.text)

    store.token = jwt('uB')
    store.user = userB as never // another account
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 400)) // dialog leave transition

    expect(document.body.textContent).not.toContain(source.text)
    expect(wrapper.text()).not.toContain('Answer')
    unmount()
  })

  it('ends the session while the explanation dialog is open without a render error', async () => {
    const errors: unknown[] = []
    const { wrapper, store, unmount } = await mountRag((err) => { errors.push(err) })
    answers['/api/rag'] = () => json({ rag_answer: 'Answer that can be explained [doc 1]', sources: [source], response_id: 'x', time_spent: 1 })
    answers['/api/rag/explain'] = () => json({ explanation: 'Because of [doc 1]' })
    await ask(wrapper, 'Question')

    // Select the answer's text and ask for an explanation, as a user does.
    const answerText = wrapper.findAll('.markdown-body').at(-1)!
    const range = document.createRange()
    range.selectNodeContents(answerText.element)
    range.getClientRects = () => [{ right: 10, bottom: 10 }] as unknown as DOMRectList // jsdom has no layout
    window.getSelection()!.removeAllRanges()
    window.getSelection()!.addRange(range)
    await answerText.trigger('mouseup')
    await wrapper.findAll('button').find((b) => b.text() === 'Explain')!.trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('Because of')

    store.forgetSession()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 400)) // dialog leave transition

    expect(errors).toEqual([])
    expect(document.body.textContent).not.toContain('Because of')
    unmount()
  })

  it('keeps a conversation started signed out when the user signs in', async () => {
    const { wrapper, store, unmount } = await mountRag()
    store.forgetSession()
    await flushPromises()
    answers['/api/rag'] = () => json({ rag_answer: 'Public answer', sources: [source], response_id: 'x', time_spent: 1 })
    await ask(wrapper, 'Anonymous question')

    store.token = jwt('uA')
    store.user = userA as never
    await flushPromises()

    expect(wrapper.text()).toContain('Public answer')
    unmount()
  })
})
