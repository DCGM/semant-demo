import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, effectScope, h } from 'vue'
import { QueryClient, useQuery, VueQueryPlugin } from '@tanstack/vue-query'

import { SEARCH_VECTORS_FRESH_MS, useSearchVectors } from 'src/features/search/useSearchVectors'
import { createAppQueryClient, queryClient, userScopedKey } from 'src/shared/query'
import { useSessionScope } from 'src/app/session'
import { useUserStore } from 'src/features/auth/userStore'

// Server-state queries (#630, #631): the app's query client and its defaults, the cached
// search vectors, and the session boundary for user-scoped queries.

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

  it('serves pages asking at once with one request, and later visits within the hour from it', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    getVectors.mockResolvedValue(VECTORS)
    const first = mountWith(client)
    const second = mountWith(client)
    expect(first.text()).toBe('loading')
    await flushPromises()

    expect([first.text(), second.text()]).toEqual(['fake-default,fake-small', 'fake-default,fake-small'])
    first.unmount()
    second.unmount()
    vi.setSystemTime(Date.now() + SEARCH_VECTORS_FRESH_MS - 1000)
    const later = mountWith(client)
    await flushPromises()
    expect(later.text()).toBe('fake-default,fake-small')
    expect(getVectors).toHaveBeenCalledTimes(1)

    later.unmount()
    vi.setSystemTime(Date.now() + 2000)
    mountWith(client)
    await flushPromises()
    expect(getVectors).toHaveBeenCalledTimes(2)
  })

  it('reports a failed load without retrying it, and asks again on the next visit', async () => {
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

  it('drops the previous user\'s queries on sign-out, also an answer still under way, and keeps shared ones', async () => {
    const scope = effectScope()
    scope.run(useSessionScope)
    const user = useUserStore()
    user.user = { id: 'u1', email: 'u1@example.com' }
    await flushPromises()

    const statsKey = userScopedKey('u1', 'collection-stats', 'A')
    queryClient.setQueryData(statsKey, { documents: 3 })
    queryClient.setQueryData(['search', 'vectors'], VECTORS)
    let answerLate: (value: unknown) => void = () => undefined
    const membersKey = userScopedKey('u1', 'collection-members', 'A')
    const loadingMembers = queryClient.fetchQuery({ queryKey: membersKey, queryFn: () => new Promise((resolve) => { answerLate = resolve }) })
      .catch((e: unknown) => e) // cancelled at sign-out

    user.user = null // sign-out
    await flushPromises()
    answerLate(['u1-only member'])
    await loadingMembers

    expect(queryClient.getQueryData(statsKey)).toBeUndefined()
    expect(queryClient.getQueryData(membersKey)).toBeUndefined()
    expect(queryClient.getQueryData(['search', 'vectors'])).toEqual(VECTORS)
    scope.stop()
  })
})
