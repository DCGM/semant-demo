import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { Dialog, QLayout, QPageContainer, Quasar } from 'quasar'
import { RouterView, createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h } from 'vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import CollectionAnnotationsPage from 'src/features/annotations/concordance/CollectionAnnotationsPage.vue'
import { useConcordanceStore } from 'src/features/annotations/concordance/concordanceStore'
import { useAnnotationSelectionStore } from 'src/features/annotations/annotationSelectionStore'

// The statistics view of the annotation workspace page (#818): the toggle writes `?view=`, a
// category narrows the shared query and returns to the list with the other filters kept, and a
// review made while the statistics are shown reads them again.

const statistics = {
  population: 'filtered',
  self_exclusion: false,
  facets: [
    { facet: 'type', values: [{ value: 'pos', count: 4 }], missing: 0, total: 4 },
    { facet: 'tag', values: [{ value: 't1', count: 3 }, { value: 't2', count: 1 }], missing: 0, total: 4 },
    { facet: 'year', values: [{ value: '1912', count: 4 }], missing: 0, total: 4 },
    { facet: 'document', values: [{ value: 'd1', count: 4 }], missing: 0, total: 4, distinct: 1 },
    { facet: 'library', values: [], missing: 4, total: 4 },
    { facet: 'language', values: [], missing: 4, total: 4 }
  ]
}

describe('the statistics view of the annotations page', () => {
  const originalFetch = globalThis.fetch
  let requests: { path: string, method: string, body: Record<string, unknown> | undefined }[]

  beforeEach(() => {
    setActivePinia(createPinia())
    requests = []
    globalThis.fetch = vi.fn(async (input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => {
      const path = new URL(String(input)).pathname
      const method = init?.method ?? 'GET'
      requests.push({ path, method, body: typeof init?.body === 'string' ? JSON.parse(init.body) : undefined })
      const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (path.endsWith('/annotations/facets')) {
        const body = typeof init?.body === 'string' ? JSON.parse(init.body) : {}
        return json(body.self_exclusion === false ? statistics : { population: 'filtered', self_exclusion: true, facets: [] })
      }
      if (path.endsWith('/annotations/review')) return json({ succeeded: ['a1'], failed: [], versions: { a1: 2 }, previous: {} })
      if (path.endsWith('/annotations/ids')) return json({ ids: [], versions: {} })
      if (path.endsWith('/annotations/documents')) return json([{ id: 'd1', title: 'Listy', available: true, count: 4 }])
      if (path.endsWith('/annotations')) return json({ rows: [], total: 0, offset: 0, limit: 50 })
      return json([])
    }) as typeof fetch
  })
  afterEach(() => {
    globalThis.fetch = originalFetch
    document.body.innerHTML = ''
  })

  async function mountPage (query = '') {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ name: 'collectionAnnotations', path: '/collections/:collectionId/annotations', component: CollectionAnnotationsPage }]
    })
    await router.push(`/collections/c1/annotations${query}`)
    await router.isReady()
    const InLayout = defineComponent({ render: () => h(QLayout, () => [h(QPageContainer, () => h(RouterView))]) })
    const wrapper = mount(InLayout, {
      global: { plugins: [router, [Quasar, { plugins: { Dialog } }], [VueQueryPlugin, { queryClient: new QueryClient() }]] as never },
      attachTo: document.body
    })
    await flushPromises()
    return { wrapper, router }
  }

  const statisticsReads = () => requests.filter(r => r.path.endsWith('/facets') && r.body?.self_exclusion === false)

  it('switches between list and statistics through the route, reading statistics only when shown', async () => {
    const { wrapper, router } = await mountPage()
    expect(statisticsReads()).toHaveLength(0)
    await wrapper.get('[data-testid="annotations-view-statistics"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ view: 'statistics' })
    expect(statisticsReads()).toHaveLength(1)
    expect(wrapper.get('[data-testid="statistics-summary"]').text()).toContain('confirmed, proposals')
    expect(wrapper.find('[data-testid="export-csv"]').exists()).toBe(false)

    await wrapper.get('[data-testid="annotations-view-list"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({})
    expect(wrapper.find('[data-testid="annotation-statistics"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('lists exactly a category: the query narrowed to it, other filters kept, back in the list', async () => {
    const store = useConcordanceStore()
    const { wrapper, router } = await mountPage('?view=statistics')
    await store.setFilters({ text: 'Karel', documentFilters: { yearMin: 1900 } })
    await flushPromises()
    await wrapper.get('[data-testid="statistics-tag-show-t2"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({})
    expect(store.filters).toMatchObject({ tagIds: ['t2'], text: 'Karel', documentFilters: { yearMin: 1900 } })
    expect(wrapper.find('[data-testid="annotation-statistics"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('reads the statistics again after a review made while they are shown', async () => {
    const { wrapper } = await mountPage('?view=statistics')
    useAnnotationSelectionStore().add([['a1', 1]])
    await flushPromises()
    const before = statisticsReads().length
    await wrapper.get('[data-testid="review-reject"]').trigger('click')
    await flushPromises()
    const ok = Array.from(document.body.querySelectorAll('.q-dialog button')).find(b => b.textContent?.includes('Reject'))
    ;(ok as HTMLButtonElement | undefined)?.click()
    await flushPromises()
    expect(requests.some(r => r.path.endsWith('/annotations/review'))).toBe(true)
    expect(statisticsReads().length).toBe(before + 1)
    wrapper.unmount()
  })
})
