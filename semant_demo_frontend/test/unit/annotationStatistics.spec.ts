import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { computed, defineComponent, h, ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { Quasar } from 'quasar'

import { SpanType, type AnnotationFacets, type Facet } from 'src/generated/api'
import { defaultFilters, withMode, type ConcordanceFilters } from 'src/features/annotations/concordance/concordanceStore'
import AnnotationStatisticsPanel from 'src/features/annotations/statistics/AnnotationStatisticsPanel.vue'
import { useAnnotationStatistics } from 'src/features/annotations/statistics/useAnnotationStatistics'
import {
  denominatorText, distributionRows, drillChange, formatShare, orderedRows, statisticsRequest, summaryOf, type Labels
} from 'src/features/annotations/statistics/statistics'

// The statistics of the annotation workspace query (#818): one population for every distribution
// (facets without self-exclusion), named denominators, Missing rows, and a drill-down that lists
// exactly a category's annotations (the query narrowed to it); ranked scopes are labelled and not
// drilled; a failed read is an error, never zeros.

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

  it('orders rows by count or by value, the Missing row last', () => {
    const rows = distributionRows(statistics().facets[2], 'year', labels, defaultFilters(), true)
    expect(orderedRows(rows, 'year', 'count').map(r => r.key)).toEqual(['1912', '1850', '__missing__'])
    expect(orderedRows(rows, 'year', 'value').map(r => r.key)).toEqual(['1850', '1912', '__missing__'])
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

describe('the statistics view', () => {
  const originalFetch = globalThis.fetch
  let requests: { path: string, body: Record<string, unknown> | undefined }[]
  let answer: () => Response | Promise<Response>

  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

  beforeEach(() => {
    setActivePinia(createPinia())
    requests = []
    answer = () => json(statistics())
    globalThis.fetch = vi.fn(async (input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => {
      const path = new URL(String(input)).pathname
      requests.push({ path, body: typeof init?.body === 'string' ? JSON.parse(init.body) : undefined })
      return path.endsWith('/facets') ? answer() : json([])
    }) as typeof fetch
  })
  afterEach(() => { globalThis.fetch = originalFetch })

  /** The panel with the statistics read as the annotations page reads them. */
  async function mountPanel (initial: ConcordanceFilters = defaultFilters(), dimension: string | null = null) {
    const filters = ref(initial)
    let emitted: unknown[][] = []
    const Host = defineComponent({
      setup () {
        const { statistics, error, load, loading } = useAnnotationStatistics(computed(() => 'c1'), filters)
        const summary = computed(() => (statistics.value ? summaryOf(statistics.value) : null))
        return () => h('div', [
          summary.value ? h('p', { 'data-testid': 'summary' }, `${summary.value.total} / ${summary.value.documents ?? '—'} / ${summary.value.denominator}`) : null,
          h(AnnotationStatisticsPanel, {
            filters: filters.value,
            statistics: statistics.value,
            error: error.value,
            stale: loading.value,
            tags: labels.tags,
            documents: labels.documents,
            dimension: dimension as never,
            onDrill: (c: unknown) => emitted.push(['drill', c]),
            onDimension: (d: unknown) => emitted.push(['dimension', d]),
            onRetry: () => { void load() }
          })
        ])
      }
    })
    const wrapper = mount(Host, { global: { plugins: [Quasar] } })
    await flushPromises()
    return Object.assign(wrapper, {
      filters,
      events: (name: string) => emitted.filter(e => e[0] === name).map(e => e.slice(1)),
      reset: () => { emitted = [] }
    })
  }

  const statisticsCalls = () => requests.filter(r => r.path.endsWith('/facets'))

  it('counts the query of the list, again when the query changes but not when its order does', async () => {
    const wrapper = await mountPanel()
    expect(statisticsCalls()).toHaveLength(1)
    expect(statisticsCalls()[0].body).toMatchObject({ self_exclusion: false, types: ['pos', 'auto'] })
    expect(wrapper.get('[data-testid="summary"]').text()).toBe('6 / 1 / of all 6 annotations matching the query')

    wrapper.filters.value = { ...defaultFilters(), types: [SpanType.pos, SpanType.auto, SpanType.neg] }
    await flushPromises()
    expect(statisticsCalls().at(-1)?.body).toMatchObject({ types: ['pos', 'auto', 'neg'] })
    const before = statisticsCalls().length
    wrapper.filters.value = { ...defaultFilters(), types: [SpanType.pos, SpanType.auto, SpanType.neg], descending: true }
    await flushPromises()
    expect(statisticsCalls()).toHaveLength(before)
  })

  it('lists exactly a category when its label is clicked; a Missing row has no link', async () => {
    const wrapper = await mountPanel()
    await wrapper.get('[data-testid="statistics-tag-show-t2"]').trigger('click')
    expect(wrapper.events('drill')[0]).toEqual([{ tagIds: ['t2'] }])
    expect(wrapper.find('[data-testid="statistics-year-show-__missing__"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="statistics-year"]').text()).toContain('Unknown year')
  })

  it('keeps cards short and shows every row in the detail', async () => {
    const many = Array.from({ length: 12 }, (_, i) => [String(1900 + i), i + 1] as [string, number])
    const counted = statistics()
    answer = () => json({ ...counted, facets: counted.facets.map(f => (f.facet === 'year' ? facet('year', many, 2, 80) : f)) })
    const wrapper = await mountPanel()
    expect(wrapper.findAll('[data-testid="statistics-year"] tbody tr')).toHaveLength(9) // 8 years and Unknown
    await wrapper.get('[data-testid="statistics-year-all"]').trigger('click')
    expect(wrapper.events('dimension')[0]).toEqual(['year'])

    const detail = await mountPanel(defaultFilters(), 'year')
    expect(detail.findAll('[data-testid="statistics-detail-year"] tbody tr')).toHaveLength(13)
    await detail.get('[data-testid="statistics-back"]').trigger('click')
    expect(detail.events('dimension')[0]).toEqual([null])
  })

  it('labels a ranked top k and offers no drill-down', async () => {
    answer = () => json(statistics({ population: 'top_k', k: 100 }))
    const wrapper = await mountPanel(withMode({ ...defaultFilters(), similarity: 'řečník' }))
    expect(statisticsCalls()[0].body).toMatchObject({ ranking: { mode: 'hybrid' }, ranking_query: 'řečník' })
    expect(wrapper.get('[data-testid="statistics-top-k"]').text()).toContain('100 most similar')
    expect(wrapper.text()).toContain('not the whole collection')
    expect(wrapper.find('[data-testid="statistics-tag-show-t1"]').exists()).toBe(false)
  })

  it('says when a distribution could not be counted, instead of showing zeros', async () => {
    const counted = statistics()
    answer = () => json({ ...counted, facets: counted.facets.filter(f => !['year', 'document', 'library', 'language'].includes(f.facet)) })
    const wrapper = await mountPanel()
    expect(wrapper.find('[data-testid="statistics-year-unavailable"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="summary"]').text()).toMatch(/^6 \/ — \//)
  })

  it('shows a failed read as an error with a retry, never as zero counts', async () => {
    answer = () => json({ detail: 'x' }, 500)
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const wrapper = await mountPanel()
    expect(wrapper.get('[data-testid="statistics-error"]').text()).toContain('Failed to load the statistics.')
    expect(wrapper.find('[data-testid="summary"]').exists()).toBe(false)
    answer = () => json(statistics())
    await wrapper.get('[data-testid="statistics-error"] button').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="summary"]').text()).toMatch(/^6 \//)
  })

  it('shows a refused query as an error, not as no annotations', async () => {
    answer = () => json({ detail: 'Too many annotations to compare' }, 400)
    const wrapper = await mountPanel()
    expect(wrapper.get('[data-testid="statistics-error"]').text()).toContain('could not be computed for this query')
    expect(wrapper.find('[data-testid="statistics-empty"]').exists()).toBe(false)
  })

  it('offers no drill-down while a newer query is counted', async () => {
    const wrapper = await mountPanel()
    expect(wrapper.find('[data-testid="statistics-tag-show-t2"]').exists()).toBe(true)
    let release!: () => void
    answer = () => { const r = json(statistics()); return new Promise<Response>(resolve => { release = () => resolve(r) }) }
    wrapper.filters.value = { ...defaultFilters(), text: 'Karel' }
    await flushPromises()
    expect(wrapper.find('[data-testid="statistics-tag-show-t2"]').exists()).toBe(false) // old counts, new filters
    release()
    await flushPromises()
    expect(wrapper.find('[data-testid="statistics-tag-show-t2"]').exists()).toBe(true)
  })
})
