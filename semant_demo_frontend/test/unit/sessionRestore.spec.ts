import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Notify, Quasar } from 'quasar'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, effectScope, h } from 'vue'
import { createMemoryHistory, createRouter, RouterView, type RouteRecordRaw, type Router } from 'vue-router'

import { useUserStore } from 'src/features/auth/userStore'
import { useSessionScope } from 'src/app/session'
import { installAuthGuard } from 'src/router/authGuard'
import { captureSession, getAuthToken, setAuthToken, useApi } from 'src/shared/api'
import LoginDialog from 'src/features/auth/LoginDialog.vue'
import MainLayout from 'src/app/MainLayout.vue'

// #319 (first part): availability is not authentication. Only a rejected token ends a
// session; offline or a server error leaves a verified session untouched, and a stored
// session that cannot be verified awaits verification instead of looking signed out.

const userA = { id: 'uA', email: 'a@example.com', username: 'a', name: 'User A' }
const userB = { id: 'uB', email: 'b@example.com', username: 'b', name: 'User B' }
const Page = defineComponent({ render: () => h('div', 'page') })
const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/search' },
  { name: 'search', path: '/search', component: Page },
  { name: 'rag', path: '/rag', component: Page },
  { name: 'about', path: '/about', component: Page },
  { name: 'feedback', path: '/feedback', component: Page },
  { name: 'sessionPending', path: '/session-pending', component: Page },
  {
    name: 'collections',
    path: '/collections',
    meta: { requiresAuth: true },
    component: RouterView,
    children: [{ name: 'collectionOverview', path: ':collectionId/overview', component: Page }]
  }
]

// An unsigned JWT-shaped token for `sub` (the backend issues `sub` = user id).
function jwt (sub: string, nonce = '1'): string {
  const encode = (value: object) => btoa(JSON.stringify(value)).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_')
  return `${encode({ alg: 'HS256' })}.${encode({ sub, n: nonce })}.sig`
}
const tokenA = jwt('uA')

type Answer = () => Response | Promise<Response>
// Answers by request path, consumed in order; the last one repeats. No answer: pending.
let answers: Record<string, Answer[]>
let sent: string[]
const originalFetch = globalThis.fetch

const json = (body: unknown, status = 200): Answer => () =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const offline: Answer = () => Promise.reject(new TypeError('Failed to fetch'))
const serverError = json({ detail: 'Service Unavailable' }, 503)
const rejected = json({ detail: 'Unauthorized' }, 401)

interface Notice { message: string }

function stubNotify () {
  const original = Notify.create
  const shown: Notice[] = []
  const create = vi.fn((options: Notice) => { shown.push(options); return () => undefined })
  Notify.create = create as unknown as typeof Notify.create
  return { create, messages: () => shown.map((notice) => notice.message), restore: () => { Notify.create = original } }
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  answers = {}
  sent = []
  globalThis.fetch = vi.fn((input: Parameters<typeof fetch>[0]) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const path = new URL(url, 'http://localhost').pathname
    sent.push(path)
    const queue = answers[path]
    if (!queue?.length) return new Promise<Response>(() => undefined)
    const answer = queue.length > 1 ? queue.shift()! : queue[0]!
    return Promise.resolve().then(answer)
  }) as typeof fetch
})

afterEach(() => {
  globalThis.fetch = originalFetch
  localStorage.clear()
})

/** A page load with a stored token whose account is not read yet. */
function storedSession (token = tokenA) {
  setAuthToken(token)
  const store = useUserStore()
  store.token = token // the store may exist already (session scope)
  return store
}

/** A verified session of user A. */
function signedIn () {
  const store = storedSession()
  store.user = userA as never
  return store
}

function guardedRouter (store = useUserStore()) {
  const router = createRouter({ history: createMemoryHistory(), routes })
  const denied = { count: 0 }
  installAuthGuard(router, store, () => { denied.count++ })
  return { router, denied }
}

const routeOf = (router: Router) => router.currentRoute.value

describe('restoring a stored session', () => {
  it.each([
    ['the server is unreachable', offline],
    ['the server fails', serverError]
  ])('keeps the token and awaits verification when %s', async (_, answer) => {
    const store = storedSession()
    answers['/api/users/me'] = [answer]

    await store.restoreSession()

    expect([store.isLoggedIn, store.awaitingVerification, store.restoreFailed]).toEqual([false, true, true])
    expect([store.token, getAuthToken()]).toEqual([tokenA, tokenA])
  })

  it('ends the session when the token is rejected', async () => {
    const store = storedSession()
    answers['/api/users/me'] = [rejected]

    await store.restoreSession()

    expect([store.awaitingVerification, store.restoreFailed, store.token, getAuthToken()]).toEqual([false, false, null, null])
  })

  it('asks again only on an explicit retry, which verifies the session once the server answers', async () => {
    const store = storedSession()
    answers['/api/users/me'] = [serverError, json(userA)]

    await store.restoreSession()
    await store.restoreSession() // layout start-up after the guard: no second request
    expect(sent).toEqual(['/api/users/me'])
    await store.restoreSession({ retry: true })

    expect([store.isLoggedIn, store.awaitingVerification, store.restoreFailed, store.getUserId]).toEqual([true, false, false, 'uA'])
  })

  it('a failure answered after sign-out leaves nothing to retry', async () => {
    const store = storedSession()
    let fail!: () => void
    answers['/api/users/me'] = [() => new Promise<Response>((resolve) => { fail = () => resolve(serverError()) })]
    const restoring = store.restoreSession()
    await flushPromises()

    store.forgetSession()
    fail()
    await restoring

    expect([store.awaitingVerification, store.restoreFailed, store.token]).toEqual([false, false, null])
  })

  it('signs out a session awaiting verification here at once, without asking the server', async () => {
    const store = storedSession()
    answers['/api/users/me'] = [offline]
    await store.restoreSession()

    await store.logout()

    expect([store.awaitingVerification, store.token, getAuthToken()]).toEqual([false, null, null])
    expect(sent).toEqual(['/api/users/me'])
  })
})

describe('a verified session on network and server errors', () => {
  let scope: ReturnType<typeof effectScope>
  let notify: ReturnType<typeof stubNotify>

  beforeEach(() => {
    notify = stubNotify()
    scope = effectScope()
    scope.run(() => useSessionScope())
  })
  afterEach(() => {
    scope.stop()
    notify.restore()
  })

  it.each([
    ['an unreachable server', offline],
    ['a server error', serverError]
  ])('keeps identity, token, route and user data on %s', async (_, answer) => {
    const store = signedIn()
    const { router } = guardedRouter(store)
    await router.push('/collections/c1/overview')
    const sessionCurrent = captureSession()
    answers['/api/user_collections'] = [answer]

    await expect(useApi().default.fetchCollectionsApiUserCollectionsGet()).rejects.toThrow()
    await flushPromises()

    expect([store.isLoggedIn, store.getUserId, store.token, getAuthToken()]).toEqual([true, 'uA', tokenA, tokenA])
    expect(routeOf(router).fullPath).toBe('/collections/c1/overview')
    expect(sessionCurrent()).toBe(true) // user-scoped state was not cleared
    expect(notify.create).not.toHaveBeenCalled()
  })
})

describe('protected route while the session cannot be verified', () => {
  it('waits on the pending route with the requested destination, without the signed-out notice', async () => {
    const store = storedSession()
    answers['/api/users/me'] = [offline]
    const { router, denied } = guardedRouter(store)

    await router.push('/collections/c1/overview?tab=tags')

    expect(routeOf(router).name).toBe('sessionPending')
    expect(routeOf(router).query.redirect).toBe('/collections/c1/overview?tab=tags')
    expect([denied.count, store.awaitingVerification, getAuthToken()]).toEqual([0, true, tokenA])
  })

  it('opens the requested destination once a retry verifies the session', async () => {
    const store = storedSession()
    answers['/api/users/me'] = [serverError, json(userA)]
    const { router } = guardedRouter(store)
    await router.push('/collections/c1/overview')

    await store.restoreSession({ retry: true })
    await flushPromises()

    expect(routeOf(router).fullPath).toBe('/collections/c1/overview')
    expect(store.isLoggedIn).toBe(true)
  })

  it('goes to search when the session ends there (Sign out, or another tab signed out)', async () => {
    const store = storedSession()
    answers['/api/users/me'] = [offline]
    const { router } = guardedRouter(store)
    await router.push('/collections')

    await store.adoptStoredToken(null)
    await flushPromises()

    expect(routeOf(router).name).toBe('search')
  })

  it('drops the requested destination when another account signs in meanwhile', async () => {
    const store = storedSession()
    answers['/api/users/me'] = [offline, json(userB)]
    const { router } = guardedRouter(store)
    await router.push('/collections/c1/overview')

    await store.adoptStoredToken(jwt('uB'))
    await flushPromises()

    expect(routeOf(router).name).toBe('search')
    expect(store.getUserId).toBe('uB')
  })

  it('keeps the destination for a new token of the same user', async () => {
    const store = storedSession()
    answers['/api/users/me'] = [offline, json(userA)]
    const { router } = guardedRouter(store)
    await router.push('/collections/c1/overview')

    await store.adoptStoredToken(jwt('uA', '2'))
    await flushPromises()

    expect(routeOf(router).fullPath).toBe('/collections/c1/overview')
  })

  it('is left at once without a session, and opens only in-app destinations when verified', async () => {
    const { router } = guardedRouter()
    await router.push('/session-pending?redirect=/collections')
    expect(routeOf(router).name).toBe('search')

    signedIn()
    await router.push('/session-pending?redirect=/collections')
    expect(routeOf(router).fullPath).toBe('/collections')
    for (const redirect of ['//evil.example/x', 'https://evil.example/', '/session-pending', '/no-such-page']) {
      await router.push({ name: 'sessionPending', query: { redirect } })
      expect(routeOf(router).name, redirect).toBe('search')
    }
  })
})

describe('session scope retries', () => {
  let scope: ReturnType<typeof effectScope>

  beforeEach(() => {
    scope = effectScope()
    scope.run(() => useSessionScope())
  })
  afterEach(() => { scope.stop() })

  it.each(['online', 'focus'])('retries a failed verification on %s, and only while it is failed', async (event) => {
    const store = storedSession()
    answers['/api/users/me'] = [offline, json(userA)]
    await store.restoreSession()
    expect(sent).toEqual(['/api/users/me'])

    window.dispatchEvent(new Event(event))
    await flushPromises()

    expect([store.isLoggedIn, sent.length]).toEqual([true, 2])
    window.dispatchEvent(new Event(event)) // verified: nothing left to retry
    await flushPromises()
    expect(sent.length).toBe(2)
  })

  it('keeps awaiting verification while a retry is under way and after it fails again', async () => {
    const store = storedSession()
    let fail!: () => void
    answers['/api/users/me'] = [offline, () => new Promise<Response>((resolve) => { fail = () => resolve(serverError()) })]
    await store.restoreSession()

    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    expect([store.awaitingVerification, store.restoreFailed]).toEqual([true, true])
    fail()
    await flushPromises()

    expect([store.awaitingVerification, store.restoreFailed, getAuthToken()]).toEqual([true, true, tokenA])
  })

  it('stops retrying when the scope ends', async () => {
    const store = storedSession()
    answers['/api/users/me'] = [offline]
    await store.restoreSession()

    scope.stop()
    window.dispatchEvent(new Event('online'))
    await flushPromises()

    expect(sent).toEqual(['/api/users/me'])
  })
})

describe('MainLayout while the session awaits verification', () => {
  // The page load of a stored session whose verification fails.
  async function mountLayout () {
    const pinia = createPinia()
    setActivePinia(pinia)
    setAuthToken(tokenA)
    const router = createRouter({ history: createMemoryHistory(), routes })
    await router.push('/search')
    const wrapper = mount(MainLayout, {
      global: {
        plugins: [[Quasar, { plugins: { Notify } }], pinia, router],
        stubs: { RightSidebar: true, LoginDialog: true, RegisterDialog: true, UserInfoDialog: true, AboutAppDialog: true }
      }
    })
    await flushPromises()
    return { wrapper, store: useUserStore() }
  }

  type Wrapper = Awaited<ReturnType<typeof mountLayout>>['wrapper']
  const drawerLabels = (wrapper: Wrapper) => wrapper.findAll('.drawer-item .item-label').map((item) => item.text())
  const banner = (wrapper: Wrapper) => wrapper.find('.session-banner')
  const bannerButton = (wrapper: Wrapper, label: string) =>
    banner(wrapper).findAll('button').find((button) => button.text() === label)!

  it('shows neither the signed-out menu nor user pages, and keeps Sign out', async () => {
    answers['/api/users/me'] = [serverError]
    const { wrapper } = await mountLayout()

    expect(banner(wrapper).text()).toContain('Your session could not be verified')
    expect(drawerLabels(wrapper)).toContain('Sign out')
    expect(drawerLabels(wrapper).filter((label) => ['Log in', 'Register', 'Collections', 'Settings'].includes(label))).toEqual([])
  })

  it('Sign out ends it here without a server answer', async () => {
    answers['/api/users/me'] = [offline]
    const { wrapper, store } = await mountLayout()

    await bannerButton(wrapper, 'Sign out').trigger('click')
    await flushPromises()

    expect([store.token, getAuthToken()]).toEqual([null, null])
    expect(sent).not.toContain('/api/auth/jwt/logout')
    expect(document.body.textContent).toContain('You have been logged out.')
    expect(banner(wrapper).exists()).toBe(false)
    expect(drawerLabels(wrapper)).toEqual(expect.arrayContaining(['Log in', 'Register']))
  })

  it('Retry verifies the session once the server answers, and keeps the banner while it does not', async () => {
    answers['/api/users/me'] = [serverError, serverError, json(userA)]
    const { wrapper, store } = await mountLayout()

    await bannerButton(wrapper, 'Retry').trigger('click')
    await flushPromises()
    expect([banner(wrapper).exists(), store.awaitingVerification]).toEqual([true, true])

    await bannerButton(wrapper, 'Retry').trigger('click')
    await flushPromises()

    expect([banner(wrapper).exists(), store.isLoggedIn]).toEqual([false, true])
    expect(drawerLabels(wrapper)).toEqual(expect.arrayContaining(['Collections', 'Settings', 'Sign out']))
  })
})

describe('signing in', () => {
  const login = json({ access_token: 'token-new', token_type: 'bearer' })

  async function submit (email = 'a', password = 'secret') {
    const wrapper = mount(LoginDialog, {
      props: { modelValue: true },
      global: {
        plugins: [[Quasar, { plugins: { Notify } }]],
        stubs: { QDialog: { template: '<div><slot /></div>' } }
      }
    })
    await wrapper.findAll('input')[0]!.setValue(email)
    await wrapper.findAll('input')[1]!.setValue(password)
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    return wrapper
  }

  it('drops the new session when its account cannot be read, and says the server failed', async () => {
    const notify = stubNotify()
    answers['/api/auth/jwt/login'] = [login]
    answers['/api/users/me'] = [serverError]
    try {
      const wrapper = await submit()
      const store = useUserStore()

      expect(wrapper.text()).toContain('the server is unreachable or failing')
      expect([store.isLoggedIn, store.awaitingVerification, store.token, getAuthToken()]).toEqual([false, false, null, null])
      expect(notify.create).not.toHaveBeenCalled()
    } finally {
      notify.restore()
    }
  })

  it('tells rejected credentials from an unreachable server', async () => {
    answers['/api/auth/jwt/login'] = [json({ detail: 'LOGIN_BAD_CREDENTIALS' }, 400)]
    expect((await submit()).text()).toContain('Invalid email or password.')

    answers['/api/auth/jwt/login'] = [offline]
    expect((await submit()).text()).toContain('Could not sign in: the server is unreachable or failing.')
  })

  it('signs in when both answers arrive', async () => {
    const notify = stubNotify()
    answers['/api/auth/jwt/login'] = [login]
    answers['/api/users/me'] = [json(userA)]
    try {
      await submit()
      const store = useUserStore()

      expect([store.isLoggedIn, store.getUserId, getAuthToken()]).toEqual([true, 'uA', 'token-new'])
    } finally {
      notify.restore()
    }
  })
})
