import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { QLayout, QPageContainer, Quasar } from 'quasar'
import { RouterView, createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h } from 'vue'

import { SpanType, type AnnotationFacets, type Facet } from 'src/generated/api'
import { defaultFilters, useConcordanceStore, withMode } from 'src/features/annotations/concordance/concordanceStore'
import AnnotationStatisticsPage from 'src/features/annotations/statistics/AnnotationStatisticsPage.vue'
import {
  denominatorText, distributionRows, drillChange, formatShare, statisticsRequest, type Labels
} from 'src/features/annotations/statistics/statistics'

// The statistics of the annotation workspace query (#818): one population for every distribution
// (facets without self-exclusion), named denominators, Missing rows, and a drill-down that lists
// exactly a category's annotations (the query narrowed to it); ranked scopes are labelled and not
// drilled; a failed read is an error, never zeros.

vi.mock('src/shared/visualization/VegaChart.vue', () => ({ default: { name: 'VegaChart', props: ['spec', 'label', 'clickable'], render: () => null } }))

const labels: Labels = {
  tags: [{ id: 't1', name: 'Speaker' }, { id: 't2', name: 'Topic' }] as Labels['tags'],
  documents: [{ id: 'd1', title: 'Národní listy', available: true, count: 3 }] as Labels['documents']
}

const facet = (name: string, values: [string, number][], missing = 0, total = 6, extra: Partial<Facet> = {}): Facet =>
  ({ facet: name, values: values.map(([value, count]) => ({ value, count })), missing, total, ...extra })

const statistics = (extra: Partial<AnnotationFacets> = {}): AnnotationFacets => ({
  population: 'filtered',
  selfExclusion: false,
  facets: [
    facet('type', [['auto', 2], ['pos', 4]]),
    facet('tag', [['t1', 5], ['t2', 1]]),
    facet('year', [['1912', 3], ['1850', 1]], 2),
    facet('document', [['d1', 6]], 0, 6, { distinct: 1, truncated: false }),
    facet('library', [['mzk', 6]]),
    facet('language', [['ces', 4]], 2)
  ],
  ...extra
} as AnnotationFacets)

describe('statistics computations', () => {
  it('asks for every distribution over the query itself', () => {
    const f = { ...defaultFilters(), tagIds: ['t1'], text: 'slovo' }
    expect(statisticsRequest(f)).toMatchObject({
      tagIds: ['t1'],
      q: 'slovo',
      types: ['pos', 'auto'],
      selfExclusion: false,
      facets: ['type', 'tag', 'year', 'document', 'library', 'language']
    })
  })

  it('orders rows, adds the Missing row and gives shares of the total', () => {
    const f = defaultFilters()
    const years = distributionRows(statistics().facets[2], 'year', labels, f, true)
    expect(years.map(r => [r.label, r.count])).toEqual([['1850', 1], ['1912', 3], ['Unknown year', 2]])
    expect(years.map(r => r.share)).toEqual([1 / 6, 3 / 6, 2 / 6])
    expect(years[2]).toMatchObject({ kind: 'missing', drill: null })
    const statuses = distributionRows(statistics().facets[0], 'type', labels, f, true)
    expect(statuses.map(r => r.label)).toEqual(['Confirmed', 'Proposals'])
    expect(distributionRows(statistics().facets[1], 'tag', labels, f, true).map(r => r.label)).toEqual(['Speaker', 'Topic'])
  })

  it('narrows the query to exactly one category, keeping every other filter', () => {
    const f = {
      ...defaultFilters(),
      tagIds: ['t1', 't2'],
      types: [SpanType.pos, SpanType.auto],
      documentFilters: { yearMin: 1800, yearMax: 1950, titleContains: ['listy'], libraries: ['mzk', 'nkp'] }
    }
    expect(drillChange('tag', 't2', f)).toEqual({ tagIds: ['t2'] })
    expect(drillChange('type', 'auto', f)).toEqual({ types: ['auto'] })
    expect(drillChange('document', 'd1', f)).toEqual({ documentIds: ['d1'] })
    expect(drillChange('year', '1912', f)).toEqual({
      documentFilters: { yearMin: 1912, yearMax: 1912, titleContains: ['listy'], libraries: ['mzk', 'nkp'] }
    })
    expect(drillChange('library', 'nkp', f)).toEqual({
      documentFilters: { yearMin: 1800, yearMax: 1950, titleContains: ['listy'], libraries: ['nkp'] }
    })
    expect(drillChange('language', 'ces', f).documentFilters).toMatchObject({ languages: ['ces'], libraries: ['mzk', 'nkp'] })
  })

  it('offers no drill-down when it would not reproduce the counts', () => {
    const rows = distributionRows(statistics().facets[1], 'tag', labels, defaultFilters(), false)
    expect(rows.every(r => r.drill === null)).toBe(true)
  })

  it('names the denominator, and a top k as not the whole collection', () => {
    expect(denominatorText(statistics(), 1234)).toBe('of all 1,234 annotations matching the query')
    expect(denominatorText(statistics({ population: 'top_k', k: 100 }), 80))
      .toBe('of the 80 annotations retrieved in the top 100 — not the whole collection')
    expect([0, 1, 0.0004, 1 / 3].map(formatShare)).toEqual(['0 %', '100 %', '<0.1 %', '33.3 %'])
  })
})

describe('the statistics page', () => {
  const originalFetch = globalThis.fetch
  let requests: { path: string, body: Record<string, unknown> | undefined }[]
  let answer: () => Response

  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

  beforeEach(() => {
    setActivePinia(createPinia())
    requests = []
    answer = () => json(statistics())
    globalThis.fetch = vi.fn(async (input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => {
      const path = new URL(String(input)).pathname
      requests.push({ path, body: typeof init?.body === 'string' ? JSON.parse(init.body) : undefined })
      if (path.endsWith('/facets')) return answer()
      if (path.endsWith('/annotations/documents')) return json(labels.documents)
      if (path.endsWith('/ids')) return json({ ids: [], versions: {} })
      if (path.endsWith('/annotations')) return json({ rows: [], total: 0, offset: 0, limit: 50 })
      return json([])
    }) as typeof fetch
  })
  afterEach(() => { globalThis.fetch = originalFetch })

  async function mountPage () {
    const Page = { render: () => null }
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { name: 'collectionStatistics', path: '/collections/:collectionId/statistics', component: AnnotationStatisticsPage },
        { name: 'collectionAnnotations', path: '/collections/:collectionId/annotations', component: Page }
      ]
    })
    await router.push('/collections/c1/statistics')
    await router.isReady()
    const InLayout = defineComponent({ render: () => h(QLayout, () => [h(QPageContainer, () => h(RouterView))]) })
    const wrapper = mount(InLayout, { global: { plugins: [router, Quasar] } })
    await flushPromises()
    return { wrapper, router }
  }

  const statisticsCalls = () => requests.filter(r => r.path.endsWith('/facets'))

  it('shows the totals of the workspace query and reads them again when the query changes', async () => {
    const { wrapper } = await mountPage()
    expect(statisticsCalls()).toHaveLength(1)
    expect(statisticsCalls()[0].body).toMatchObject({ self_exclusion: false, types: ['pos', 'auto'] })
    expect(wrapper.get('[data-testid="statistics-total"]').text()).toBe('6')
    expect(wrapper.get('[data-testid="statistics-documents"]').text()).toBe('1')
    expect(wrapper.get('[data-testid="statistics-summary"]').text()).toContain('confirmed (66.7 %)')
    expect(wrapper.find('[data-testid="statistics-top-k"]').exists()).toBe(false)

    await wrapper.get('[data-testid="statistics-status-neg"]').trigger('click')
    await flushPromises()
    expect(useConcordanceStore().filters.types).toEqual(['pos', 'auto', 'neg'])
    expect(statisticsCalls().at(-1)?.body).toMatchObject({ types: ['pos', 'auto', 'neg'] })

    const before = statisticsCalls().length
    await useConcordanceStore().setFilters({ descending: true })
    await flushPromises()
    expect(statisticsCalls()).toHaveLength(before) // the order of the list does not change the counts
  })

  it('lists exactly a category in the annotation list', async () => {
    const { wrapper, router } = await mountPage()
    await wrapper.get('[data-testid="statistics-tag-show-t2"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('collectionAnnotations')
    expect(useConcordanceStore().filters.tagIds).toEqual(['t2'])
    expect(wrapper.find('[data-testid="statistics-year-show-__missing__"]').exists()).toBe(false)
  })

  it('labels a ranked top k and offers no drill-down', async () => {
    answer = () => json(statistics({ population: 'top_k', k: 100 }))
    useConcordanceStore().enter('c1')
    useConcordanceStore().filters = withMode({ ...defaultFilters(), similarity: 'řečník' })
    const { wrapper } = await mountPage()
    expect(statisticsCalls()[0].body).toMatchObject({ ranking: { mode: 'hybrid' }, ranking_query: 'řečník' })
    expect(wrapper.get('[data-testid="statistics-top-k"]').text()).toContain('top 100')
    expect(wrapper.text()).toContain('not the whole collection')
    expect(wrapper.find('[data-testid="statistics-tag-show-t1"]').exists()).toBe(false)
  })

  it('says when a distribution could not be counted, instead of showing zeros', async () => {
    const counted = statistics()
    answer = () => json({ ...counted, facets: counted.facets.filter(f => !['year', 'document', 'library', 'language'].includes(f.facet)) })
    const { wrapper } = await mountPage()
    expect(wrapper.find('[data-testid="statistics-year-unavailable"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="statistics-documents"]').text()).toBe('—')
  })

  it('shows a failed read as an error with a retry, never as zero counts', async () => {
    answer = () => json({ detail: 'x' }, 500)
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const { wrapper } = await mountPage()
    expect(wrapper.get('[data-testid="statistics-error"]').text()).toContain('Failed to load the statistics.')
    expect(wrapper.find('[data-testid="statistics-total"]').exists()).toBe(false)
    answer = () => json(statistics())
    await wrapper.get('[data-testid="statistics-error"] button').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="statistics-total"]').text()).toBe('6')
  })
})
