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
import { useRightSidebarStore } from 'src/app/sidebar/rightSidebarStore'

// The Statistics panel of the annotation workspace sidebar (#680): the compact counts of the same
// query as the Statistics view, a value narrowing the list beside it, nothing read while it is
// closed, and a re-read after a review.

const tagValues = Array.from({ length: 7 }, (_, i) => ({ value: `t${i + 1}`, count: 10 - i }))
const statistics = {
  population: 'filtered',
  self_exclusion: false,
  facets: [
    { facet: 'type', values: [{ value: 'pos', count: 40 }], missing: 0, total: 40 },
    { facet: 'tag', values: tagValues, missing: 2, total: 40, distinct: 7 },
    { facet: 'year', values: [{ value: '1912', count: 40 }], missing: 0, total: 40 },
    { facet: 'document', values: [{ value: 'd1', count: 40 }], missing: 0, total: 40, distinct: 1 },
    { facet: 'library', values: [], missing: 40, total: 40 },
    { facet: 'language', values: [], missing: 40, total: 40 }
  ]
}

describe('the statistics panel of the annotations sidebar', () => {
  const originalFetch = globalThis.fetch
  let requests: { path: string, body: Record<string, unknown> | undefined }[]
  let failStatistics = false

  beforeEach(() => {
    setActivePinia(createPinia())
    requests = []
    failStatistics = false
    globalThis.fetch = vi.fn(async (input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => {
      const path = new URL(String(input)).pathname
      const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined
      requests.push({ path, body })
      const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
      if (path.endsWith('/annotations/facets')) {
        if (body?.self_exclusion === false) return failStatistics ? json({ detail: 'x' }, 500) : json(statistics)
        return json({ population: 'filtered', self_exclusion: true, facets: [] })
      }
      if (path.endsWith('/annotations/review')) return json({ succeeded: ['a1'], failed: [], versions: { a1: 2 }, previous: {} })
      if (path.endsWith('/annotations/ids')) return json({ ids: [], versions: {} })
      if (path.endsWith('/annotations/documents')) return json([{ id: 'd1', title: 'Listy', available: true, count: 40 }])
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
    // The sidebar shell (RightSidebar.vue) is not mounted: its target element stands in for it.
    const target = document.createElement('div')
    document.body.appendChild(target)
    useRightSidebarStore().targetEl = target
    const InLayout = defineComponent({ render: () => h(QLayout, () => [h(QPageContainer, () => h(RouterView))]) })
    const wrapper = mount(InLayout, {
      global: { plugins: [router, [Quasar, { plugins: { Dialog } }], [VueQueryPlugin, { queryClient: new QueryClient() }]] as never },
      attachTo: document.body
    })
    await flushPromises()
    return { wrapper, router, sidebar: useRightSidebarStore() }
  }

  const reads = () => requests.filter(r => r.path.endsWith('/facets') && r.body?.self_exclusion === false)
  const q = (testId: string) => document.body.querySelector<HTMLElement>(`[data-testid="${testId}"]`)

  it('starts as the rail of icons, Annotation unavailable until a row is open, and reads nothing', async () => {
    const sidebar = useRightSidebarStore()
    sidebar.open = true // what the shell does when a page brings its first panel
    const { wrapper } = await mountPage()
    expect(sidebar.open).toBe(true)
    expect(sidebar.miniState).toBe(true)
    expect(sidebar.sortedPanels.map(p => [p.label, p.disabled])).toEqual([['Annotation', true], ['Statistics', false]])
    expect(sidebar.activePanelId).toBe('annotation-statistics')
    sidebar.activate('annotation-context') // a disabled panel cannot be chosen
    expect(sidebar.activePanelId).toBe('annotation-statistics')
    expect(reads()).toHaveLength(0)
    // choosing the Statistics expands the rail and reads
    sidebar.activate('annotation-statistics')
    await flushPromises()
    expect(sidebar.miniState).toBe(false)
    expect(reads()).toHaveLength(1)
    wrapper.unmount()
  })

  it('is registered after the annotation panel and reads nothing while the sidebar is closed', async () => {
    const { wrapper, sidebar } = await mountPage()
    expect(sidebar.sortedPanels.map(p => p.label)).toEqual(['Annotation', 'Statistics'])
    expect(sidebar.sortedPanels[1]).toMatchObject({ icon: 'bar_chart', order: 2 })
    expect(reads()).toHaveLength(0)
    sidebar.open = true
    await flushPromises()
    expect(reads()).toHaveLength(1)
    // The request is the view's: every facet over its own population.
    expect(reads()[0].body).toMatchObject({ self_exclusion: false })
    sidebar.open = false
    await flushPromises()
    expect(reads()).toHaveLength(1)
    wrapper.unmount()
  })

  it('shows the summary and the five most frequent values with the Missing row, the rest behind "All rows"', async () => {
    const { wrapper, sidebar } = await mountPage()
    sidebar.open = true
    await flushPromises()
    expect(q('statistics-sidebar-total')?.textContent).toBe('40')
    expect(q('statistics-sidebar-documents')?.textContent).toBe('1')
    const tagRows = document.body.querySelectorAll('[data-testid="statistics-sidebar-table-tag"] tbody tr')
    expect(tagRows).toHaveLength(6) // five values and the Missing row
    expect(q('statistics-sidebar-tag-all')?.textContent).toContain('All 8 rows')
    wrapper.unmount()
  })

  it('narrows the filter by a value without switching the main view', async () => {
    const store = useConcordanceStore()
    const { wrapper, router, sidebar } = await mountPage('?view=statistics')
    await store.setFilters({ text: 'Karel' })
    sidebar.open = true
    await flushPromises()
    q('statistics-sidebar-table-tag-show-t2')?.click()
    await flushPromises()
    expect(store.filters).toMatchObject({ tagIds: ['t2'], text: 'Karel' })
    expect(router.currentRoute.value.query).toEqual({ view: 'statistics' })
    wrapper.unmount()
  })

  it('opens the full view, of everything or of one distribution', async () => {
    const { wrapper, router, sidebar } = await mountPage()
    sidebar.open = true
    await flushPromises()
    q('statistics-sidebar-open')?.click()
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ view: 'statistics' })
    q('statistics-sidebar-tag-all')?.click()
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ view: 'statistics', dimension: 'tag' })
    wrapper.unmount()
  })

  it('reads again after a review and on a query change', async () => {
    const store = useConcordanceStore()
    const { wrapper, sidebar } = await mountPage()
    sidebar.open = true
    useAnnotationSelectionStore().add([['a1', 1]])
    await flushPromises()
    const before = reads().length
    await store.setFilters({ text: 'Karel' })
    await flushPromises()
    expect(reads().length).toBe(before + 1)
    document.body.querySelector<HTMLElement>('[data-testid="review-reject"]')?.click()
    await flushPromises()
    const ok = Array.from(document.body.querySelectorAll('.q-dialog button')).find(b => b.textContent?.includes('Reject'))
    ;(ok as HTMLButtonElement | undefined)?.click()
    await flushPromises()
    expect(requests.some(r => r.path.endsWith('/annotations/review'))).toBe(true)
    expect(reads().length).toBe(before + 2)
    wrapper.unmount()
  })

  it('says a failed read is an error with Retry, never zeros', async () => {
    failStatistics = true
    const { wrapper, sidebar } = await mountPage()
    sidebar.open = true
    await flushPromises()
    expect(q('statistics-sidebar-error')).not.toBeNull()
    expect(q('statistics-sidebar-total')).toBeNull()
    failStatistics = false
    q('statistics-sidebar-retry')?.click()
    await flushPromises()
    expect(q('statistics-sidebar-error')).toBeNull()
    expect(q('statistics-sidebar-total')?.textContent).toBe('40')
    wrapper.unmount()
  })
})
