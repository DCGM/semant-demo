import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { computed, defineComponent, effectScope, h } from 'vue'
import { focusManager, onlineManager, QueryClient, useQuery, VueQueryPlugin } from '@tanstack/vue-query'

import { SEARCH_VECTORS_KEY, useSearchVectors } from 'src/features/search/useSearchVectors'
import { createAppQueryClient, queryClient, userScopedKey } from 'src/shared/query'
import { useSessionScope } from 'src/app/session'
import { useUserStore } from 'src/features/auth/userStore'

// Server-state queries (#630, #631): the app's query client and its defaults, the cached
// search vectors, and the session boundary, which keeps only queries marked shared.

const getVectors = vi.fn()

vi.mock('src/shared/api', async () => ({
  ...(await vi.importActual<typeof import('src/shared/api')>('src/shared/api')),
  useApi: () => ({ default: { getAvailableSearchVectorsApiSearchVectorsGet: getVectors } })
}))

const VECTORS = {
  vectors: [{ id: 'fake-default', name: 'Fake default', description: '' }, { id: 'fake-small', name: 'Fake small', description: '' }],
  defaultVector: 'fake-default'
}

/** A page that shows the search vectors as Search does: loading, failed or the list. */
const VectorsPage = defineComponent({
  setup () {
    const { data, isError } = useSearchVectors()
    return () => h('p', isError.value ? 'failed' : data.value ? data.value.vectors.map(v => v.id).join(',') : 'loading')
  }
})

// Pages still mounted: unmounted after each test (`unmountPages`), so no test leaves a
// client subscribed to the global focus and online managers.
const pages: Set<{ unmount: () => void }> = new Set()

function mountWith (client: QueryClient, component = VectorsPage) {
  const page = mount(component, { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } })
  pages.add(page)
  return page
}

function unmount (page: { unmount: () => void }) {
  pages.delete(page)
  page.unmount()
}

function unmountPages () {
  for (const page of [...pages]) unmount(page)
}

describe('search vectors', () => {
  let client: QueryClient

  beforeEach(() => {
    client = createAppQueryClient()
    getVectors.mockReset()
  })

  afterEach(() => {
    unmountPages()
    client.clear()
    vi.useRealTimers()
  })

  it('serves pages asking at once with one request, and later visits until a reload from it', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    getVectors.mockResolvedValue(VECTORS)
    const first = mountWith(client)
    const second = mountWith(client)
    expect(first.text()).toBe('loading')
    await flushPromises()

    expect([first.text(), second.text()]).toEqual(['fake-default,fake-small', 'fake-default,fake-small'])
    unmount(first)
    unmount(second)
    vi.setSystemTime(Date.now() + 24 * 60 * 60 * 1000) // a day later, the tab still open
    const later = mountWith(client)
    await flushPromises()
    expect(later.text()).toBe('fake-default,fake-small')
    expect(getVectors).toHaveBeenCalledTimes(1)
  })

  it('reports a failed load without retrying it, and a page mounting the query anew asks again', async () => {
    getVectors.mockRejectedValueOnce(new Error('503')).mockResolvedValue(VECTORS)
    const page = mountWith(client)
    await flushPromises()

    expect(page.text()).toBe('failed')
    expect(getVectors).toHaveBeenCalledTimes(1)
    unmount(page)

    const again = mountWith(client)
    await flushPromises()
    expect(again.text()).toBe('fake-default,fake-small')
    expect(getVectors).toHaveBeenCalledTimes(2)
  })
})

describe('app query defaults', () => {
  let client: QueryClient

  beforeEach(() => {
    client = createAppQueryClient()
  })

  afterEach(() => {
    unmountPages()
    client.clear()
    onlineManager.setOnline(true)
    focusManager.setFocused(undefined)
  })

  /** A page showing a query that is stale at once (no `staleTime`), as most queries are. */
  function stalePage (client: QueryClient) {
    const read = vi.fn().mockResolvedValue('answer')
    const Page = defineComponent({
      setup () {
        const { data } = useQuery({ queryKey: ['stale-at-once'], queryFn: read })
        return () => h('p', data.value ?? 'loading')
      }
    })
    return { read, page: mountWith(client, Page) }
  }

  it('sends a request also after the browser reported being offline, and lets it fail', async () => {
    getVectors.mockReset().mockRejectedValue(new TypeError('Failed to fetch'))
    onlineManager.setOnline(false)
    const page = mountWith(client)
    await flushPromises()

    expect(getVectors).toHaveBeenCalledTimes(1)
    expect(page.text()).toBe('failed')
  })

  it('does not refetch a stale query when the tab regains focus', async () => {
    const { read, page } = stalePage(client)
    await flushPromises()
    expect(page.text()).toBe('answer')

    focusManager.setFocused(false)
    focusManager.setFocused(true)
    await flushPromises()

    expect(read).toHaveBeenCalledTimes(1)
  })

  it('does not refetch a stale query when the connection returns', async () => {
    const { read, page } = stalePage(client)
    await flushPromises()
    expect(page.text()).toBe('answer')

    onlineManager.setOnline(false)
    onlineManager.setOnline(true)
    await flushPromises()

    expect(read).toHaveBeenCalledTimes(1)
  })
})

/** An answer the test gives later; `answer` settles it. */
function held<T> () {
  let answer: (value: T) => void = () => undefined
  const promise = new Promise<T>((resolve) => { answer = resolve })
  return { promise, answer }
}

/** A page showing one query of the app's client, as a kept-alive page or the layout does. */
function shownQuery (key: string, read: () => Promise<string>) {
  const Page = defineComponent({
    setup () {
      const { data } = useQuery({ queryKey: [key], queryFn: read })
      return () => h('p', data.value ?? 'loading')
    }
  })
  return mountWith(queryClient, Page)
}

describe('session boundary', () => {
  let scope: ReturnType<typeof effectScope>

  beforeEach(() => {
    setActivePinia(createPinia())
    scope = effectScope()
    scope.run(useSessionScope)
  })

  afterEach(() => {
    unmountPages()
    scope.stop()
    queryClient.clear()
  })

  async function signIn (id: string) {
    useUserStore().user = { id, email: `${id}@example.com` }
    await flushPromises()
  }

  async function signOut () {
    useUserStore().user = null
    await flushPromises()
  }

  it('drops queries nobody shows and finished mutations at sign-out, also an answer under way, and keeps shared ones', async () => {
    await signIn('u1')
    const statsKey = userScopedKey('u1', 'collection-stats', 'A')
    queryClient.setQueryData(statsKey, { documents: 3 })
    // A user-dependent read whose key forgot the user: dropped all the same.
    queryClient.setQueryData(['collections'], [{ id: 'A' }])
    getVectors.mockReset().mockResolvedValue(VECTORS)
    const searchPage = mountWith(queryClient) // the real search-vector query, marked shared
    await flushPromises()
    const late = held<string[]>()
    const membersKey = userScopedKey('u1', 'collection-members', 'A')
    const loadingMembers = queryClient.fetchQuery({ queryKey: membersKey, queryFn: () => late.promise })
      .catch((e: unknown) => e) // cancelled at sign-out
    await queryClient.getMutationCache().build(queryClient, { mutationFn: (name: string) => Promise.resolve(name) })
      .execute('Private collection of u1')

    await signOut()
    late.answer(['u1-only member'])
    await loadingMembers

    expect(queryClient.getQueryData(statsKey)).toBeUndefined()
    expect(queryClient.getQueryData(['collections'])).toBeUndefined()
    expect(queryClient.getQueryData(membersKey)).toBeUndefined()
    expect(queryClient.getMutationCache().getAll()).toEqual([])
    expect(queryClient.getQueryData(SEARCH_VECTORS_KEY)).toEqual(VECTORS)
    expect(searchPage.text()).toBe('fake-default,fake-small')
    expect(getVectors).toHaveBeenCalledTimes(1)
  })

  it('asks a query still shown again under the new session, without showing the old answer or loading forever', async () => {
    await signIn('u1')
    const again = held<string>()
    const collections = vi.fn().mockResolvedValueOnce('collections of u1').mockReturnValueOnce(again.promise)
    const loadingForU1 = held<string>()
    const permissions = vi.fn().mockReturnValueOnce(loadingForU1.promise).mockResolvedValueOnce('permissions of nobody')
    const collectionsPage = shownQuery('collections', collections)
    const permissionsPage = shownQuery('permissions', permissions)
    await flushPromises()
    expect([collectionsPage.text(), permissionsPage.text()]).toEqual(['collections of u1', 'loading'])

    await signOut()

    expect(collectionsPage.text()).toBe('loading') // asked again, the old answer gone
    expect(permissionsPage.text()).toBe('permissions of nobody') // not stuck on the cancelled request
    again.answer('collections of nobody')
    loadingForU1.answer('permissions of u1')
    await flushPromises()
    expect([collectionsPage.text(), permissionsPage.text()]).toEqual(['collections of nobody', 'permissions of nobody'])
  })

  it('takes the old answer from a shown query that is disabled without a user', async () => {
    await signIn('u1')
    const Page = defineComponent({
      setup () {
        const user = useUserStore()
        const { data } = useQuery({
          queryKey: ['own-collections'],
          queryFn: () => Promise.resolve('collections of u1'),
          enabled: computed(() => !!user.getUserId)
        })
        return () => h('p', data.value ?? 'none')
      }
    })
    const page = mountWith(queryClient, Page)
    await flushPromises()
    expect(page.text()).toBe('collections of u1')

    await signOut()

    expect(page.text()).toBe('none')
  })

  it('asks the queries cached while signed out again when a user signs in', async () => {
    const quota = vi.fn().mockResolvedValueOnce('allowance of a guest').mockResolvedValueOnce('allowance of u1')
    const page = shownQuery('quota', quota)
    queryClient.setQueryData(['public-read'], 'read as a guest')
    await flushPromises()
    expect(page.text()).toBe('allowance of a guest')

    await signIn('u1')

    expect(page.text()).toBe('allowance of u1')
    expect(queryClient.getQueryData(['public-read'])).toBeUndefined()
  })
})
