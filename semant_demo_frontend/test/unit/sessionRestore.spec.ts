import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Notify, Quasar } from 'quasar'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, effectScope, h } from 'vue'
import { createMemoryHistory, createRouter, type RouteRecordRaw } from 'vue-router'

import { useUserStore } from 'src/features/auth/userStore'
import { useSessionScope } from 'src/app/session'
import { installAuthGuard } from 'src/router/authGuard'
import { getAuthToken, setAuthToken } from 'src/shared/api'
import LoginDialog from 'src/features/auth/LoginDialog.vue'

// #319 (first part): only a rejected token ends a stored session. Offline or a server
// error while reading the account keeps the token, says so and lets the user retry.

const user = { id: 'u1', email: 'u1@example.com', username: 'u1', name: 'User One' }
const Page = defineComponent({ render: () => h('div', 'page') })
const routes: RouteRecordRaw[] = [
  { name: 'search', path: '/search', component: Page },
  { name: 'collections', path: '/collections', meta: { requiresAuth: true }, component: Page }
]

type Answer = () => Response | Promise<Response>
// Answers by request path, consumed in order; the last one repeats.
let answers: Record<string, Answer[]>
let sent: string[]
const originalFetch = globalThis.fetch

const json = (body: unknown, status = 200): Answer => () =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const offline: Answer = () => Promise.reject(new TypeError('Failed to fetch'))
const serverError = json({ detail: 'Internal Server Error' }, 500)
const rejected = json({ detail: 'Unauthorized' }, 401)

interface Notice { message: string, actions?: Array<{ label?: string, handler?: () => void }> }

function stubNotify () {
  const original = Notify.create
  const shown: Notice[] = []
  const dismiss = vi.fn()
  const create = vi.fn((options: Notice) => { shown.push(options); return dismiss })
  Notify.create = create as unknown as typeof Notify.create
  return { create, dismiss, last: () => shown.at(-1)!, restore: () => { Notify.create = original } }
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
function storedSession () {
  setAuthToken('token-1')
  const store = useUserStore()
  store.token = 'token-1' // the store may exist already (session scope)
  return store
}

describe('restoring a stored session', () => {
  it.each([
    ['the server is unreachable', offline],
    ['the server fails', serverError]
  ])('keeps the token when %s', async (_, answer) => {
    const store = storedSession()
    answers['/api/users/me'] = [answer]

    await store.restoreSession()

    expect([store.isLoggedIn, store.restoreFailed, store.token, getAuthToken()]).toEqual([false, true, 'token-1', 'token-1'])
  })

  it('ends the session when the token is rejected', async () => {
    const store = storedSession()
    answers['/api/users/me'] = [rejected]

    await store.restoreSession()

    expect([store.isLoggedIn, store.restoreFailed, store.token, getAuthToken()]).toEqual([false, false, null, null])
  })

  it('asks again only on an explicit retry, which signs in once the server answers', async () => {
    const store = storedSession()
    answers['/api/users/me'] = [serverError, json(user)]

    await store.restoreSession()
    await store.restoreSession() // layout start-up after the guard: no second request
    expect(sent).toEqual(['/api/users/me'])
    await store.restoreSession({ retry: true })

    expect([store.isLoggedIn, store.restoreFailed, store.getUserId]).toEqual([true, false, 'u1'])
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

    expect([store.restoreFailed, store.token, store.unconfirmedToken]).toEqual([false, null, null])
  })
})

describe('protected route while the session cannot be confirmed', () => {
  it('goes to search without the signed-out notice and keeps the token', async () => {
    const store = storedSession()
    answers['/api/users/me'] = [offline]
    const router = createRouter({ history: createMemoryHistory(), routes })
    let denied = 0
    installAuthGuard(router, store, () => { denied++ })

    await router.push('/collections')

    expect(router.currentRoute.value.name).toBe('search')
    expect([denied, store.restoreFailed, getAuthToken()]).toEqual([0, true, 'token-1'])
  })
})

describe('session scope on a session that cannot be confirmed', () => {
  let notify: ReturnType<typeof stubNotify>
  let scope: ReturnType<typeof effectScope>

  beforeEach(() => {
    notify = stubNotify()
    scope = effectScope()
    scope.run(() => useSessionScope())
  })
  afterEach(() => {
    scope.stop()
    notify.restore()
  })

  it('says so, and Retry signs in once the server answers', async () => {
    const store = storedSession()
    answers['/api/users/me'] = [serverError, json(user)]
    await store.restoreSession()
    await flushPromises()

    expect(notify.create).toHaveBeenCalledTimes(1)
    expect(notify.last().message).toContain('Could not restore your session')
    notify.last().actions!.find((action) => action.label === 'Retry')!.handler!()
    await flushPromises()

    expect([store.isLoggedIn, store.restoreFailed]).toEqual([true, false])
    expect(notify.dismiss).toHaveBeenCalledTimes(1)
    expect(notify.create).toHaveBeenCalledTimes(1)
  })

  it('reports a retry that fails again', async () => {
    const store = storedSession()
    answers['/api/users/me'] = [offline]
    await store.restoreSession()
    await flushPromises()

    notify.last().actions!.find((action) => action.label === 'Retry')!.handler!()
    await flushPromises()

    expect(notify.create).toHaveBeenCalledTimes(2)
    expect([store.restoreFailed, getAuthToken()]).toEqual([true, 'token-1'])
  })

  it('retries when the browser comes back online, and only then', async () => {
    const store = storedSession()
    answers['/api/users/me'] = [offline, json(user)]
    await store.restoreSession()
    await flushPromises()
    expect(sent).toEqual(['/api/users/me'])

    window.dispatchEvent(new Event('online'))
    await flushPromises()

    expect([store.isLoggedIn, sent.length]).toEqual([true, 2])
    window.dispatchEvent(new Event('online')) // signed in: nothing left to retry
    await flushPromises()
    expect(sent.length).toBe(2)
  })

  it('stops retrying when the scope ends', async () => {
    const store = storedSession()
    answers['/api/users/me'] = [offline]
    await store.restoreSession()
    await flushPromises()

    scope.stop()
    window.dispatchEvent(new Event('online'))
    await flushPromises()

    expect(sent).toEqual(['/api/users/me'])
    expect(notify.dismiss).toHaveBeenCalledTimes(1)
  })
})

describe('signing in', () => {
  const login = json({ access_token: 'token-new', token_type: 'bearer' })

  async function submit (email = 'u1', password = 'secret') {
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
      expect([store.isLoggedIn, store.restoreFailed, store.token, getAuthToken()]).toEqual([false, false, null, null])
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
    answers['/api/users/me'] = [json(user)]
    try {
      await submit()
      const store = useUserStore()

      expect([store.isLoggedIn, store.getUserId, getAuthToken()]).toEqual([true, 'u1', 'token-new'])
    } finally {
      notify.restore()
    }
  })
})
