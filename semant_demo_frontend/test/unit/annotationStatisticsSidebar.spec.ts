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
  let payload: unknown = statistics
  let attributes: unknown[] = []

  beforeEach(() => {
    setActivePinia(createPinia())
    requests = []
    failStatistics = false
    payload = statistics
    attributes = []
    globalThis.fetch = vi.fn(async (input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => {
      const path = new URL(String(input)).pathname
      const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined
      requests.push({ path, body })
      const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
      if (path.endsWith('/annotations/facets')) {
        if (body?.self_exclusion === false) return failStatistics ? json({ detail: 'x' }, 500) : json(payload)
        return json({ population: 'filtered', self_exclusion: true, facets: [] })
      }
      if (path.endsWith('/attributes')) return json(attributes)
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
    expect(sidebar.open).toBe(true) // beside the list on a wide screen (a phone closes it: browser test)
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

  it('counts the accepted attribute values as the view does: five values, Not assigned, the rest in the view', async () => {
    attributes = [{
      id: 'a1',
      name: 'Role',
      cardinality: 'multi',
      all_tags: true,
      tag_ids: [],
      retired: false,
      values: Array.from({ length: 7 }, (_, i) => ({ id: `v${i + 1}`, label: `Value ${i + 1}` }))
    }, { id: 'a2', name: 'Old', cardinality: 'single', all_tags: true, tag_ids: [], retired: true, values: [] }]
    payload = {
      ...statistics,
      facets: [...statistics.facets, {
        facet: 'attribute:a1',
        missing: 10,
        total: 40,
        eligible: 30,
        with_value: 20,
        assignments: 25,
        values: Array.from({ length: 7 }, (_, i) => ({ value: `v${i + 1}`, count: 7 - i, inapplicable: i === 0 ? 1 : 0 }))
      }]
    }
    const store = useConcordanceStore()
    const { wrapper, router, sidebar } = await mountPage('?view=statistics')
    sidebar.open = true
    await flushPromises()
    // The view's request and the panel's are the same, both with the current attribute only.
    const bodies = reads().map(r => r.body)
    expect(bodies.length).toBeGreaterThanOrEqual(2)
    expect(bodies.at(-1)).toEqual(bodies.at(-2))
    expect(bodies.at(-1)?.facets).toContain('attribute:a1')
    expect(bodies.at(-1)?.facets).not.toContain('attribute:a2')

    expect(q('statistics-sidebar-attribute-a1-summary')?.textContent).toContain('20 of 30')
    const rows = Array.from(document.body.querySelectorAll('[data-testid="statistics-sidebar-attribute-a1-values"] tbody tr'))
    expect(rows).toHaveLength(6) // the five most frequent values and Not assigned
    expect(rows[0].textContent).toContain('6') // retained (inapplicable) values are not counted
    expect(rows.at(-1)?.textContent).toContain('Not assigned')
    expect(q('statistics-sidebar-attribute-a2')).toBeNull()

    q('statistics-sidebar-attribute-a1-values-show-v2')!.click()
    await flushPromises()
    expect(store.filters).toMatchObject({ attributeValues: ['a1:v2'], types: ['pos'] })
    await router.push({ query: {} }) // back to the list: All values opens the full view
    await flushPromises()
    expect(q('statistics-sidebar-attribute-a1-all')?.textContent).toContain('All 7 values')
    const scrolled: Element[] = []
    const original = Element.prototype.scrollIntoView
    Element.prototype.scrollIntoView = function (this: Element) { scrolled.push(this) }
    q('statistics-sidebar-attribute-a1-all')!.click()
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ view: 'statistics' })
    // ...scrolled to that attribute's card, which would otherwise be below the distributions.
    expect(scrolled.map(e => e.getAttribute('data-testid'))).toEqual(['statistics-attribute-a1'])
    Element.prototype.scrollIntoView = original
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

  it('counts exactly what the Statistics view counts: one request, the same numbers', async () => {
    const store = useConcordanceStore()
    const { wrapper, sidebar } = await mountPage('?view=statistics')
    await store.setFilters({ text: 'Karel' })
    sidebar.open = true
    await flushPromises()
    const bodies = reads().map(r => JSON.stringify(r.body))
    expect(bodies.length).toBeGreaterThanOrEqual(2) // the view's and the panel's
    expect(new Set(bodies.slice(-2)).size).toBe(1)
    expect(q('statistics-sidebar-total')?.textContent).toBe(q('statistics-total')?.textContent)
    expect(q('statistics-sidebar-documents')?.textContent).toBe(q('statistics-documents')?.textContent)
    wrapper.unmount()
  })

  it('says a ranked top k is not the whole collection and offers no drill-down', async () => {
    payload = { ...statistics, population: 'top_k', k: 40 }
    const { wrapper, sidebar } = await mountPage()
    sidebar.open = true
    await flushPromises()
    expect(q('statistics-sidebar-top-k')?.textContent).toContain('40 most similar')
    expect(q('statistics-sidebar-table-tag-show-t2')).toBeNull()
    wrapper.unmount()
  })

  it('names a distribution the server could not count as unavailable', async () => {
    payload = { ...statistics, facets: statistics.facets.filter(f => f.facet !== 'document') }
    const { wrapper, sidebar } = await mountPage()
    sidebar.open = true
    await flushPromises()
    expect(q('statistics-sidebar-document-unavailable')).not.toBeNull()
    expect(q('statistics-sidebar-documents')?.textContent).toBe('—')
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
