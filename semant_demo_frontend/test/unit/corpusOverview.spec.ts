import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Quasar } from 'quasar'
import { effectScope, nextTick } from 'vue'

import {
  categoryBarSpec, categoryRows, coverage, languageLabel, libraryLabel, yearHistogramSpec, yearRows
} from 'src/features/analytics/corpusOverview'
import CorpusOverviewPage from 'src/features/analytics/CorpusOverviewPage.vue'
import { SLOW_AFTER_MS, useCorpusOverview } from 'src/features/analytics/useCorpusOverview'
import VegaChart from 'src/shared/visualization/VegaChart.vue'
import { loadEmbed } from 'src/shared/visualization/loadEmbed'

vi.mock('src/shared/visualization/loadEmbed', () => ({ loadEmbed: vi.fn() }))

/** Drawings made through the mocked vega-embed; `fail` makes the next ones fail. */
const embedded = {
  calls: [] as { element: HTMLElement, spec: Record<string, unknown>, options: unknown, finalize: ReturnType<typeof vi.fn> }[],
  fail: false
}

function resetEmbed () {
  embedded.calls = []
  embedded.fail = false
  vi.mocked(loadEmbed).mockResolvedValue(async (element, spec, options) => {
    if (embedded.fail) throw new Error('cannot draw')
    const finalize = vi.fn()
    embedded.calls.push({ element: element as HTMLElement, spec: spec as Record<string, unknown>, options, finalize })
    return { finalize }
  })
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

/** The backend answer (snake_case) of a corpus with 10 documents. */
const overviewBody = (changes: Record<string, unknown> = {}) => ({
  scope: 'searchable_corpus',
  unit: 'documents',
  total_documents: 10,
  computed_at: '2026-10-15T12:00:00Z',
  data_source: 'live_aggregation',
  publication_year: {
    available: true,
    bin_width_years: 10,
    bins: [{ start: 1900, end_exclusive: 1910, count: 4 }, { start: 1910, end_exclusive: 1920, count: 3 }],
    unknown_count: 3
  },
  libraries: { available: false, unavailable_reason: 'missing_property', values: null, other_count: null, unknown_count: null },
  languages: {
    available: true,
    values: [{ value: 'ces', count: 5 }, { value: 'cze', count: 2 }],
    other_count: 1,
    unknown_count: 2
  },
  ...changes
})

describe('corpus overview rows and labels', () => {
  it('names known language codes and keeps codes with the same name apart', () => {
    expect(languageLabel('ces')).toBe('Czech (ces)')
    expect(languageLabel('cze')).toBe('Czech (cze)')
    expect(languageLabel('Old Czech')).toBe('Old Czech')
    expect(libraryLabel('mzk')).toBe('Moravian Library (mzk)')
    expect(libraryLabel('svkhk')).toBe('svkhk')
  })

  it('lists values, then Other and Unknown, with their documents', () => {
    const rows = categoryRows({ available: true, values: [{ value: 'ces', count: 5 }], otherCount: 1, unknownCount: 0 }, languageLabel)
    expect(rows.map(r => [r.label, r.count, r.kind])).toEqual([
      ['Czech (ces)', 5, 'value'], ['Other values', 1, 'other'], ['Unknown', 0, 'unknown']
    ])
    expect(new Set(rows.map(r => r.key)).size).toBe(3)
    expect(categoryRows({ available: true, values: [], otherCount: 0, unknownCount: 4 }, languageLabel).map(r => r.label))
      .toEqual(['Unknown'])
    expect(categoryRows({ available: false, unavailableReason: 'missing_property' }, libraryLabel)).toEqual([])
  })

  it('labels decades by their first and last year', () => {
    expect(yearRows({ available: true, bins: [{ start: 1900, endExclusive: 1910, count: 2 }] }))
      .toEqual([{ start: 1900, endExclusive: 1910, label: '1900–1909', count: 2 }])
    expect(yearRows({ available: false })).toEqual([])
  })

  it('computes coverage, also of an empty corpus', () => {
    expect(coverage(3, 10)).toEqual({ known: 7, unknown: 3, percent: 70 })
    expect(coverage(0, 0)).toEqual({ known: 0, unknown: 0, percent: 0 })
  })

  it('titles the chart axes and tooltips in documents', () => {
    const histogram = JSON.stringify(yearHistogramSpec(yearRows(overviewBodyAsYears())))
    const bars = JSON.stringify(categoryBarSpec(categoryRows({ available: true, values: [], otherCount: 0, unknownCount: 1 }, String), 'Language'))
    for (const spec of [histogram, bars]) {
      expect(spec).toContain('"title":"Documents"')
      expect(spec).not.toMatch(/chunk|hit/i)
    }
  })
})

function overviewBodyAsYears () {
  return { available: true, bins: [{ start: 1900, endExclusive: 1910, count: 4 }] }
}

describe('VegaChart', () => {
  beforeEach(resetEmbed)

  const mountChart = (spec: Record<string, unknown>) => mount(VegaChart, { props: { spec, label: 'Chart of documents' } })

  it('draws a Vega-Lite spec at the container width as SVG and disposes of it', async () => {
    const wrapper = mountChart({ $schema: 'https://vega.github.io/schema/vega-lite/v6.json', mark: 'bar' })
    await flush()

    expect(embedded.calls).toHaveLength(1)
    const [call] = embedded.calls
    expect(call.element.getAttribute('aria-label')).toBe('Chart of documents')
    expect(call.element.getAttribute('role')).toBe('img')
    expect(call.spec).toMatchObject({ mark: 'bar', width: 400, autosize: { type: 'fit-x' } })
    expect(call.options).toMatchObject({ actions: false, renderer: 'svg' })

    wrapper.unmount()
    expect(call.finalize).toHaveBeenCalledTimes(1)
  })

  it('draws a changed spec again and disposes of the previous drawing', async () => {
    const wrapper = mountChart({ mark: 'bar' })
    await flush()
    await wrapper.setProps({ spec: { mark: 'line' } })
    await flush()

    expect(embedded.calls.map(c => c.spec.mark)).toEqual(['bar', 'line'])
    expect(embedded.calls[0].finalize).toHaveBeenCalledTimes(1)
    expect(embedded.calls[1].finalize).not.toHaveBeenCalled()
  })

  it('passes a Vega spec unchanged', async () => {
    const spec = { $schema: 'https://vega.github.io/schema/vega/v6.json', marks: [] }
    mountChart(spec)
    await flush()
    expect(embedded.calls[0].spec).toEqual(spec)
  })

  it('says so when the chart cannot be drawn', async () => {
    embedded.fail = true
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const wrapper = mountChart({ mark: 'bar' })
    await flush()
    expect(wrapper.text()).toContain('The chart could not be drawn.')
    vi.mocked(console.error).mockRestore()
  })
})

describe('CorpusOverviewPage', () => {
  let requests: { signal?: AbortSignal | null, answer: (body: unknown, status?: number) => void }[]

  beforeEach(() => {
    resetEmbed()
    requests = []
    globalThis.fetch = vi.fn((input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => new Promise<Response>((resolve, reject) => {
      expect(String(input)).toContain('/api/analytics/corpus/overview')
      init?.signal?.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })))
      requests.push({
        signal: init?.signal,
        answer: (body, status = 200) => resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
      })
    })) as typeof fetch
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  const mountPage = () => mount(CorpusOverviewPage, { global: { plugins: [[Quasar, {}]] } })

  /** The mounted page once its request has been sent (the client sends it asynchronously). */
  async function openPage () {
    const wrapper = mountPage()
    await flush()
    return wrapper
  }

  const tableText = (wrapper: ReturnType<typeof mountPage>, testId: string) =>
    wrapper.get(`[data-testid="${testId}"]`).findAll('tbody tr').map(r => r.findAll('th, td').map(c => c.text()))

  it('states its scope and shows totals, coverage, charts and tables in documents', async () => {
    const wrapper = await openPage()
    expect(wrapper.text()).toContain('Loading the corpus overview')
    expect(wrapper.get('[data-testid="corpus-scope"]').text()).toMatch(/searchable semANT corpus.*not your collections/s)

    requests[0].answer(overviewBody())
    await flushPromises()
    await flush()

    expect(wrapper.get('[data-testid="corpus-total"]').text()).toBe('10')
    expect(wrapper.get('[data-testid="corpus-freshness"]').text()).toContain('counted now')
    const years = wrapper.get('[data-testid="corpus-years"]')
    expect(years.text()).toContain('7 of 10 documents (70 %) have a publication year; 3 unknown.')
    expect(tableText(wrapper, 'corpus-years')).toEqual([['1900–1909', '4'], ['1910–1919', '3'], ['Unknown year', '3']])
    const languages = wrapper.get('[data-testid="corpus-languages"]')
    expect(languages.text()).toContain('8 of 10 documents (80 %) have a language; 2 unknown.')
    expect(tableText(wrapper, 'corpus-languages')).toEqual([
      ['Czech (ces)', 'ces', '5'], ['Czech (cze)', 'cze', '2'], ['Other values', '—', '1'], ['Unknown', '—', '2']
    ])
    // Two charts: years and languages; the library is unavailable.
    expect(embedded.calls.map(c => c.element.getAttribute('aria-label'))).toEqual([
      expect.stringContaining('per publication decade'), expect.stringContaining('per language')
    ])
  })

  it('shows an unavailable property as unavailable, not as zero', async () => {
    const wrapper = await openPage()
    requests[0].answer(overviewBody())
    await flushPromises()

    const libraries = wrapper.get('[data-testid="corpus-libraries"]')
    expect(libraries.text()).toContain('Not available')
    expect(libraries.text()).toContain('not a count of zero')
    expect(libraries.find('table').exists()).toBe(false)
  })

  it('says when the overview is a recent count served again', async () => {
    const wrapper = await openPage()
    requests[0].answer(overviewBody({ data_source: 'cached_aggregation' }))
    await flushPromises()
    expect(wrapper.get('[data-testid="corpus-freshness"]').text()).toContain('a recent count, served again')
  })

  it('shows an empty corpus without charts', async () => {
    const wrapper = await openPage()
    requests[0].answer(overviewBody({
      total_documents: 0,
      publication_year: { available: true, bin_width_years: 10, bins: [], unknown_count: 0 },
      languages: { available: true, values: [], other_count: 0, unknown_count: 0 }
    }))
    await flushPromises()

    expect(wrapper.get('[data-testid="corpus-total"]').text()).toBe('0')
    expect(wrapper.get('[data-testid="corpus-empty"]').text()).toContain('no documents')
    expect(embedded.calls).toHaveLength(0)
  })

  it('reports a failure with Retry, which loads the overview again', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const wrapper = await openPage()
    requests[0].answer({ detail: 'Internal Server Error' }, 500)
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Internal Server Error')
    expect(wrapper.find('[data-testid="corpus-total"]').exists()).toBe(false)

    const retry = wrapper.findAll('button').find(b => b.text().includes('Retry'))
    await retry!.trigger('click')
    await flush()
    expect(requests).toHaveLength(2)
    requests[1].answer(overviewBody())
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="corpus-total"]').text()).toBe('10')
  })

  it('says when loading takes long', async () => {
    vi.useFakeTimers()
    const wrapper = mountPage()
    expect(wrapper.text()).not.toContain('takes longer than usual')
    await nextTick()
    vi.advanceTimersByTime(SLOW_AFTER_MS + 1)
    await nextTick()
    expect(wrapper.text()).toContain('takes longer than usual')
  })

  it('aborts the request when the page is left', async () => {
    const wrapper = await openPage()
    const [request] = requests
    wrapper.unmount()

    expect(request.signal?.aborted).toBe(true)
  })

  it('ignores the answer of a request replaced by a newer one', async () => {
    const scope = effectScope()
    const state = scope.run(() => useCorpusOverview())!
    const first = state.load()
    await flush()
    const second = state.load()
    await flush()

    expect(requests[0].signal?.aborted).toBe(true)
    requests[1].answer(overviewBody({ total_documents: 12 }))
    requests[0].answer(overviewBody({ total_documents: 11 }))
    await Promise.all([first, second])
    expect(state.overview.value?.totalDocuments).toBe(12)
    expect(state.loading.value).toBe(false)

    const third = state.load()
    await flush()
    scope.stop()
    expect(requests[2].signal?.aborted).toBe(true)
    await third
  })
})
