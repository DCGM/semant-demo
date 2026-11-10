import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, effectScope, h } from 'vue'
import { onlineManager, QueryClient, useQuery, VueQueryPlugin } from '@tanstack/vue-query'

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

function mountWith (client: QueryClient, component = VectorsPage) {
  return mount(component, { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } })
}

describe('search vectors', () => {
  let client: QueryClient

  beforeEach(() => {
    client = createAppQueryClient()
    getVectors.mockReset()
  })

  afterEach(() => {
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
    first.unmount()
    second.unmount()
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
    page.unmount()

    const again = mountWith(client)
    await flushPromises()
    expect(again.text()).toBe('fake-default,fake-small')
    expect(getVectors).toHaveBeenCalledTimes(2)
  })
})

describe('app query defaults', () => {
  afterEach(() => {
    onlineManager.setOnline(true)
  })

  it('sends a request also after the browser reported being offline, and lets it fail', async () => {
    const client = createAppQueryClient()
    getVectors.mockReset().mockRejectedValue(new TypeError('Failed to fetch'))
    onlineManager.setOnline(false)
    const page = mountWith(client)
    await flushPromises()

    expect(getVectors).toHaveBeenCalledTimes(1)
    expect(page.text()).toBe('failed')
    client.clear()
  })

  it('does not refetch a stale query when the tab regains focus or the connection returns', async () => {
    const client = createAppQueryClient()
    const read = vi.fn().mockResolvedValue('answer')
    const Page = defineComponent({
      setup () {
        const { data } = useQuery({ queryKey: ['stale-at-once'], queryFn: read })
        return () => h('p', data.value ?? 'loading')
      }
    })
    const page = mountWith(client, Page)
    await flushPromises()
    expect(page.text()).toBe('answer')

    document.dispatchEvent(new Event('visibilitychange'))
    window.dispatchEvent(new Event('focus'))
    window.dispatchEvent(new Event('offline'))
    window.dispatchEvent(new Event('online'))
    await flushPromises()

    expect(read).toHaveBeenCalledTimes(1)
    client.clear()
  })
})

describe('session boundary', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    queryClient.clear()
  })

  it('drops every query not marked shared on sign-out, also an answer still under way', async () => {
    const scope = effectScope()
    scope.run(useSessionScope)
    const user = useUserStore()
    user.user = { id: 'u1', email: 'u1@example.com' }
    await flushPromises()

    const statsKey = userScopedKey('u1', 'collection-stats', 'A')
    queryClient.setQueryData(statsKey, { documents: 3 })
    // A user-dependent read whose key forgot the user: dropped all the same.
    queryClient.setQueryData(['collections'], [{ id: 'A' }])
    getVectors.mockReset().mockResolvedValue(VECTORS)
    const searchPage = mountWith(queryClient) // the real search-vector query, marked shared
    await flushPromises()
    let answerLate: (value: unknown) => void = () => undefined
    const membersKey = userScopedKey('u1', 'collection-members', 'A')
    const loadingMembers = queryClient.fetchQuery({ queryKey: membersKey, queryFn: () => new Promise((resolve) => { answerLate = resolve }) })
      .catch((e: unknown) => e) // cancelled at sign-out

    user.user = null // sign-out
    await flushPromises()
    answerLate(['u1-only member'])
    await loadingMembers

    expect(queryClient.getQueryData(statsKey)).toBeUndefined()
    expect(queryClient.getQueryData(['collections'])).toBeUndefined()
    expect(queryClient.getQueryData(membersKey)).toBeUndefined()
    expect(queryClient.getQueryData(SEARCH_VECTORS_KEY)).toEqual(VECTORS)
    expect(searchPage.text()).toBe('fake-default,fake-small')
    searchPage.unmount()
    scope.stop()
  })
})
