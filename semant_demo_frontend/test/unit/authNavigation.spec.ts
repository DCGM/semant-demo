import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Notify, Quasar } from 'quasar'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, effectScope, h } from 'vue'
import { createMemoryHistory, createRouter, RouterView, type RouteRecordRaw } from 'vue-router'

import { useUserStore } from 'src/stores/user-store'
import { useSessionScope } from 'src/app/session'
import { installAuthGuard } from 'src/router/authGuard'
import { clearAuthToken, createApiClients, onUnauthorized, postNdjson, setAuthToken } from 'src/shared/api'
import MainLayout from 'src/layouts/MainLayout.vue'

const user = { id: 'u1', email: 'u1@example.com', username: 'u1', name: 'User One' }
const Page = defineComponent({ render: () => h('div', 'page') })

// Notify.create exists only once the Quasar plugin is installed; replace it while a test runs.
function stubNotify () {
  const original = Notify.create
  const create = vi.fn()
  Notify.create = create as unknown as typeof Notify.create
  return { create, restore: () => { Notify.create = original } }
}

function signIn (store = useUserStore()) {
  setAuthToken('token-1')
  store.token = 'token-1'
  store.user = user as never
}

describe('401 answers', () => {
  const originalFetch = globalThis.fetch
  let status: number
  let reported: string[]
  let stop: () => void

  beforeEach(() => {
    status = 401
    reported = []
    stop = onUnauthorized((token) => reported.push(token))
    globalThis.fetch = vi.fn(() => Promise.resolve(new Response('{"detail":"Unauthorized"}', { status }))) as typeof fetch
  })

  afterEach(() => {
    stop()
    globalThis.fetch = originalFetch
    clearAuthToken()
  })

  it('report the token the request was sent with, from both transports', async () => {
    setAuthToken('token-1')
    await expect(createApiClients().default.healthHealthGet()).rejects.toThrow()
    setAuthToken('token-2')
    await expect(postNdjson('/ai/discuss_span', {}, { onValue: () => undefined })).rejects.toThrow()

    expect(reported).toEqual(['token-1', 'token-2'])
  })

  it('are not reported for anonymous requests or other errors', async () => {
    await expect(createApiClients().default.healthHealthGet()).rejects.toThrow()
    setAuthToken('token-1')
    status = 403
    await expect(createApiClients().default.healthHealthGet()).rejects.toThrow()

    expect(reported).toEqual([])
  })
})

describe('session scope on an expired session', () => {
  beforeEach(() => { setActivePinia(createPinia()) })
  afterEach(() => { clearAuthToken() })

  it('signs out when a request with the current token is rejected, not for an old token', async () => {
    const notify = stubNotify()
    const scope = effectScope()
    scope.run(useSessionScope)
    const store = useUserStore()
    signIn(store)
    const globalFetch = globalThis.fetch
    globalThis.fetch = vi.fn(() => Promise.resolve(new Response('{}', { status: 401 }))) as typeof fetch

    try {
      setAuthToken('token-old') // a request sent under an earlier token
      await expect(createApiClients().default.healthHealthGet()).rejects.toThrow()
      expect(store.isLoggedIn).toBe(true)

      setAuthToken('token-1')
      await expect(createApiClients().default.healthHealthGet()).rejects.toThrow()
      expect([store.isLoggedIn, store.token]).toEqual([false, null])
      expect(notify.create).toHaveBeenCalledWith(expect.objectContaining({ message: 'Your session has expired. Please log in again.' }))
    } finally {
      globalThis.fetch = globalFetch
      notify.restore()
      scope.stop()
    }
  })
})

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/search' },
  { name: 'search', path: '/search', component: Page },
  { name: 'about', path: '/about', component: Page },
  {
    name: 'collections',
    path: '/collections',
    meta: { requiresAuth: true },
    component: RouterView,
    children: [{ name: 'collectionOverview', path: ':collectionId/overview', component: Page }]
  }
]

describe('auth guard', () => {
  let denied: number

  function setup () {
    const store = useUserStore()
    const router = createRouter({ history: createMemoryHistory(), routes })
    installAuthGuard(router, store, () => { denied++ })
    return { store, router }
  }

  beforeEach(() => {
    setActivePinia(createPinia())
    denied = 0
  })
  afterEach(() => { clearAuthToken() })

  it('sends a signed-out direct link to a protected child route to search', async () => {
    const { router } = setup()

    await router.push('/collections/c1/overview')

    expect(router.currentRoute.value.name).toBe('search')
    expect(denied).toBe(1)
  })

  it('waits for a stored session to be restored before opening a protected route', async () => {
    setAuthToken('token-1')
    const { store, router } = setup()
    let restored!: () => void
    const fetchUser = vi.spyOn(store, 'fetchCurrentUser').mockImplementation(() => new Promise<void>((resolve) => {
      restored = () => { store.user = user as never; resolve() }
    }))

    const navigation = router.push('/collections')
    void store.restoreSession() // the layout restoring at the same time shares the request
    await flushPromises()
    restored()
    await navigation

    expect(router.currentRoute.value.name).toBe('collections')
    expect([fetchUser.mock.calls.length, denied]).toEqual([1, 0])
  })

  it('denies a protected route when the stored token is no longer valid', async () => {
    setAuthToken('expired')
    const { store, router } = setup()
    vi.spyOn(store, 'fetchCurrentUser').mockImplementation(async () => { store.forgetSession() })

    await router.push('/collections')

    expect(router.currentRoute.value.name).toBe('search')
    expect(denied).toBe(1)
  })

  it('leaves a protected route when the session ends there, and only there', async () => {
    const { store, router } = setup()
    signIn(store)
    await router.push('/about')
    store.forgetSession()
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('about')

    signIn(store)
    await router.push('/collections/c1/overview')
    store.forgetSession()
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('search')
    expect(denied).toBe(0) // whoever ended the session tells the user
  })
})

describe('MainLayout navigation', () => {
  beforeEach(() => { setActivePinia(createPinia()) })
  afterEach(() => { clearAuthToken() })

  async function mountLayout () {
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        ...routes.filter((r) => r.name !== 'search'),
        { name: 'search', path: '/search', component: Page },
        { name: 'rag', path: '/rag', component: Page },
        { name: 'feedback', path: '/feedback', component: Page }
      ]
    })
    await router.push('/search')
    const wrapper = mount(MainLayout, {
      global: {
        plugins: [[Quasar, { plugins: { Notify } }], pinia, router],
        stubs: {
          RightSidebar: true,
          LoginDialog: true,
          RegisterDialog: true,
          UserInfoDialog: true,
          AboutAppDialog: true
        }
      }
    })
    await flushPromises()
    return { wrapper, store: useUserStore() }
  }

  const drawerLabels = (wrapper: Awaited<ReturnType<typeof mountLayout>>['wrapper']) =>
    wrapper.findAll('.drawer-item .item-label').map((item) => item.text())

  it('shows Log in and Register, not protected pages or account actions, when signed out', async () => {
    const { wrapper } = await mountLayout()

    const labels = drawerLabels(wrapper)
    expect(labels).toEqual(expect.arrayContaining(['Document search', 'Chat Assistant', 'About', 'Log in', 'Register']))
    expect(labels.filter((l) => ['Collections', 'Settings', 'Sign out'].includes(l))).toEqual([])
  })

  it('switches between the signed-out and signed-in menus without a reload', async () => {
    const { wrapper, store } = await mountLayout()

    signIn(store)
    await flushPromises()
    let labels = drawerLabels(wrapper)
    expect(labels).toEqual(expect.arrayContaining(['Collections', 'Settings', 'Sign out']))
    expect(labels.filter((l) => ['Log in', 'Register'].includes(l))).toEqual([])

    store.forgetSession() // expired session or sign-out
    await flushPromises()
    labels = drawerLabels(wrapper)
    expect(labels).toEqual(expect.arrayContaining(['Log in', 'Register']))
    expect(labels.filter((l) => ['Collections', 'Settings', 'Sign out'].includes(l))).toEqual([])
  })

  it('keeps the same items in the collapsed drawer', async () => {
    const { wrapper, store } = await mountLayout()
    signIn(store)
    await flushPromises()
    const iconsOf = () => wrapper.findAll('.drawer-item .q-item__section--avatar .q-icon').map((i) => i.text())
    const expanded = iconsOf()

    await wrapper.findComponent({ name: 'MiniStateButton' }).trigger('click')
    await flushPromises()

    expect(iconsOf()).toEqual(expanded)
    expect(expanded).toEqual(expect.arrayContaining(['folder', 'settings', 'logout']))
  })

  it('signs out from the drawer', async () => {
    const { wrapper, store } = await mountLayout()
    signIn(store)
    await flushPromises()
    const logout = vi.spyOn(store, 'logout').mockImplementation(async () => { store.forgetSession() })
    const signOut = wrapper.findAll('.drawer-item').find((item) => item.text().includes('Sign out'))
    await signOut?.trigger('click')
    await flushPromises()

    expect(logout).toHaveBeenCalledOnce()
    expect(drawerLabels(wrapper)).toEqual(expect.arrayContaining(['Log in']))
    expect(document.body.textContent).toContain('You have been logged out.')
  })
})
