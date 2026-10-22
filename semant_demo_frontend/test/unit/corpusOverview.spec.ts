import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Quasar } from 'quasar'
import { effectScope, nextTick } from 'vue'

import {
  categoryBarSpec, categoryRows, coverage, decadeRows, filterChips, isUnfiltered, languageLabel, libraryLabel,
  withoutFilter, yearHistogramSpec
} from 'src/features/analytics/corpusOverview'
import CorpusOverviewPage from 'src/features/analytics/CorpusOverviewPage.vue'
import { SLOW_AFTER_MS, useCorpusOverview } from 'src/features/analytics/useCorpusOverview'
import VegaChart from 'src/shared/visualization/VegaChart.vue'
import { loadEmbed } from 'src/shared/visualization/loadEmbed'

vi.mock('src/shared/visualization/loadEmbed', () => ({ loadEmbed: vi.fn() }))

/**
 * Drawings made through the mocked vega-embed; `fail` makes the next ones fail. With `held`,
 * a drawing finishes only when its `finish` is called, so drawings can finish in any order.
 */
const embedded = {
  calls: [] as {
    element: HTMLElement, spec: Record<string, unknown>, options: unknown,
    finalize: ReturnType<typeof vi.fn>, finish: () => void
  }[],
  fail: false,
  held: false
}

function resetEmbed () {
  embedded.calls = []
  embedded.fail = false
  embedded.held = false
  vi.mocked(loadEmbed).mockResolvedValue(async (element, spec, options) => {
    if (embedded.fail) throw new Error('cannot draw')
    const el = element as HTMLElement
    const finalize = vi.fn()
    let finish = () => undefined as void
    const finished = new Promise<void>((resolve) => { finish = resolve })
    embedded.calls.push({ element: el, spec: spec as Record<string, unknown>, options, finalize, finish })
    if (embedded.held) await finished
    // vega-embed clears and fills the element it is given.
    el.innerHTML = `<svg data-mark="${String((spec as { mark?: unknown }).mark)}"></svg>`
    return { finalize }
  })
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

const NO_FILTERS = { year_min: null, year_max: null, title_contains: null, libraries: [], languages: [] }

/** The backend answer (snake_case) of a corpus with 10 documents, unfiltered unless `filters` is given. */
const overviewBody = (changes: Record<string, unknown> = {}) => ({
  scope: 'searchable_corpus',
  unit: 'documents',
  filters: NO_FILTERS,
  total_documents: 10,
  computed_at: '2026-10-15T12:00:00Z',
  data_source: 'live_aggregation',
  publication_year: {
    available: true,
    years: [{ year: 1905, count: 4 }, { year: 1910, count: 2 }, { year: 1919, count: 1 }],
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

  it('groups years into decades labelled by their first and last year, keeping empty decades', () => {
    expect(decadeRows({ available: true, years: [{ year: 1871, count: 1 }, { year: 1909, count: 2 }, { year: 1910, count: 3 }] }))
      .toEqual([
        { start: 1870, endExclusive: 1880, label: '1870–1879', count: 1 },
        { start: 1880, endExclusive: 1890, label: '1880–1889', count: 0 },
        { start: 1890, endExclusive: 1900, label: '1890–1899', count: 0 },
        { start: 1900, endExclusive: 1910, label: '1900–1909', count: 2 },
        { start: 1910, endExclusive: 1920, label: '1910–1919', count: 3 }
      ])
    expect(decadeRows({ available: true, years: [], unknownCount: 2 })).toEqual([])
    expect(decadeRows({ available: false })).toEqual([])
  })

  it('names each applied filter and removes one of them', () => {
    const filters = { yearMin: 1900, yearMax: 1920, titleContains: 'Pražský věstník', libraries: ['mzk', 'svkhk'], languages: ['ces'] }
    expect(filterChips(filters).map(c => c.label)).toEqual([
      'Years: 1900–1920', 'Title: Pražský věstník', 'Library: Moravian Library (mzk), svkhk', 'Language: Czech (ces)'
    ])
    expect(filterChips({ yearMin: 1909 }).map(c => c.label)).toEqual(['Years: from 1909'])
    expect(filterChips({ yearMax: 1909 }).map(c => c.label)).toEqual(['Years: until 1909'])
    expect(filterChips({ yearMin: 1909, yearMax: 1909 }).map(c => c.label)).toEqual(['Years: 1909'])
    expect(withoutFilter(filters, 'years')).toEqual({ titleContains: 'Pražský věstník', libraries: ['mzk', 'svkhk'], languages: ['ces'] })
    expect(isUnfiltered({ yearMin: null, yearMax: null, titleContains: null, libraries: [], languages: [] })).toBe(true)
    expect(isUnfiltered(withoutFilter({ languages: ['ces'] }, 'languages'))).toBe(true)
  })

  it('computes coverage, also of an empty corpus', () => {
    expect(coverage(3, 10)).toEqual({ known: 7, unknown: 3, percent: 70 })
    expect(coverage(0, 0)).toEqual({ known: 0, unknown: 0, percent: 0 })
  })

  it('titles the chart axes and tooltips in documents', () => {
    const histogram = JSON.stringify(yearHistogramSpec(decadeRows({ available: true, years: [{ year: 1905, count: 4 }] })))
    const bars = JSON.stringify(categoryBarSpec(categoryRows({ available: true, values: [], otherCount: 0, unknownCount: 1 }, String), 'Language'))
    for (const spec of [histogram, bars]) {
      expect(spec).toContain('"title":"Documents"')
      expect(spec).not.toMatch(/chunk|hit/i)
    }
  })
})

describe('VegaChart', () => {
  beforeEach(resetEmbed)

  const mountChart = (spec: Record<string, unknown>) => mount(VegaChart, { props: { spec, label: 'Chart of documents' } })

  it('draws a Vega-Lite spec at the container width as SVG and disposes of it', async () => {
    const wrapper = mountChart({ $schema: 'https://vega.github.io/schema/vega-lite/v6.json', mark: 'bar' })
    await flush()

    expect(embedded.calls).toHaveLength(1)
    const [call] = embedded.calls
    const canvas = wrapper.get('.vega-chart__canvas')
    expect(canvas.attributes('aria-label')).toBe('Chart of documents')
    expect(canvas.attributes('role')).toBe('img')
    expect(call.element.parentElement).toBe(canvas.element)
    expect(call.spec).toMatchObject({ mark: 'bar', width: 400, autosize: { type: 'fit-x' } })
    expect(call.options).toMatchObject({ actions: false, renderer: 'svg' })

    wrapper.unmount()
    expect(call.finalize).toHaveBeenCalledTimes(1)
  })

  const drawnMarks = (wrapper: ReturnType<typeof mountChart>) =>
    wrapper.findAll('.vega-chart__canvas svg').map(svg => svg.attributes('data-mark'))

  it('shows only the newest drawing when overlapping drawings finish out of order', async () => {
    embedded.held = true
    const wrapper = mountChart({ mark: 'bar' })
    await flush()
    await wrapper.setProps({ spec: { mark: 'line' } })
    await flush()
    expect(embedded.calls.map(c => c.spec.mark)).toEqual(['bar', 'line'])
    // Each drawing gets its own element; neither is shown before it finishes.
    expect(embedded.calls[0].element).not.toBe(embedded.calls[1].element)
    expect(drawnMarks(wrapper)).toEqual([])

    embedded.calls[1].finish()
    await flush()
    expect(drawnMarks(wrapper)).toEqual(['line'])

    // The older drawing finishes late: finalized, never shown, the newer one untouched.
    embedded.calls[0].finish()
    await flush()
    expect(embedded.calls[0].finalize).toHaveBeenCalledTimes(1)
    expect(embedded.calls[0].element.isConnected).toBe(false)
    expect(drawnMarks(wrapper)).toEqual(['line'])
    expect(embedded.calls[1].finalize).not.toHaveBeenCalled()

    wrapper.unmount()
    expect(embedded.calls[1].finalize).toHaveBeenCalledTimes(1)
  })

  it('draws again at a new width and keeps the newest drawing when a resize overlaps a spec change', async () => {
    let resized: () => void = () => undefined
    const original = Object.getOwnPropertyDescriptor(globalThis, 'ResizeObserver')
    vi.stubGlobal('ResizeObserver', class {
      constructor (callback: () => void) { resized = callback }
      observe () { /* the test calls `resized` */ }
      disconnect () { /* nothing to release */ }
    })
    let width = 300
    const clientWidth = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => width)
    try {
      embedded.held = true
      const wrapper = mountChart({ mark: 'bar' })
      await flush()
      width = 500
      resized()
      await flush()
      await wrapper.setProps({ spec: { mark: 'line' } })
      await flush()
      expect(embedded.calls.map(c => [c.spec.mark, c.spec.width])).toEqual([['bar', 300], ['bar', 500], ['line', 500]])

      // Finish newest first, then the stale ones in reverse order.
      for (const i of [2, 0, 1]) {
        embedded.calls[i].finish()
        await flush()
      }
      expect(drawnMarks(wrapper)).toEqual(['line'])
      expect(embedded.calls.map(c => c.finalize.mock.calls.length)).toEqual([1, 1, 0])
      expect(wrapper.get('.vega-chart__canvas').element.children).toHaveLength(1)
    } finally {
      clientWidth.mockRestore()
      if (original) Object.defineProperty(globalThis, 'ResizeObserver', original)
      else delete (globalThis as { ResizeObserver?: unknown }).ResizeObserver
    }
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
  let requests: { signal?: AbortSignal | null, body: unknown, answer: (body: unknown, status?: number) => void }[]

  beforeEach(() => {
    resetEmbed()
    requests = []
    globalThis.fetch = vi.fn((input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => new Promise<Response>((resolve, reject) => {
      expect(String(input)).toContain('/api/analytics/corpus/distributions')
      init?.signal?.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })))
      requests.push({
        signal: init?.signal,
        body: JSON.parse(String(init?.body)),
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
    // The corpus is effectively static: no refresh control next to the count time.
    expect(wrapper.findAll('button').map(b => b.text())).not.toContain(expect.stringContaining('Reload'))
    const years = wrapper.get('[data-testid="corpus-years"]')
    expect(years.text()).toContain('7 of 10 documents (70 %) have a publication year; 3 unknown.')
    expect(tableText(wrapper, 'corpus-years')).toEqual([['1900–1909', '4'], ['1910–1919', '3'], ['Unknown or invalid year', '3']])
    const languages = wrapper.get('[data-testid="corpus-languages"]')
    expect(languages.text()).toContain('8 of 10 documents (80 %) have a language; 2 unknown.')
    expect(tableText(wrapper, 'corpus-languages')).toEqual([
      ['Czech (ces)', 'ces', '5'], ['Czech (cze)', 'cze', '2'], ['Other values', '—', '1'], ['Unknown', '—', '2']
    ])
    // Two charts: years and languages; the library is unavailable.
    expect(wrapper.findAll('.vega-chart__canvas').map(c => c.attributes('aria-label'))).toEqual([
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
      publication_year: { available: true, years: [], unknown_count: 0 },
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

  /** The page with its whole-corpus counts loaded (filter choices from `changes`). */
  async function loadedPage (changes: Record<string, unknown> = {}) {
    const wrapper = await openPage()
    requests[0].answer(overviewBody(changes))
    await flushPromises()
    await flush()
    return wrapper
  }

  const button = (wrapper: ReturnType<typeof mountPage>, text: string) => wrapper.findAll('button').find(b => b.text().includes(text))!

  const filtered = { year_min: 1900, year_max: 1920, title_contains: 'Pražský věstník', libraries: [], languages: ['ces'] }

  it('sends no filters first and offers the whole corpus as filter choices', async () => {
    const wrapper = await loadedPage({
      libraries: { available: true, values: [{ value: 'mzk', count: 6 }], other_count: 0, unknown_count: 4 }
    })

    expect(requests[0].body).toEqual({ filters: {} })
    const panel = wrapper.get('[data-testid="corpus-filters"]')
    expect(panel.text()).toContain('ignores case, not diacritics (skola ≠ škola)')
    expect(panel.text()).toContain('Matches language values by word, ignoring case')
    expect(wrapper.get('[data-testid="corpus-total"]').text()).toBe('10')
    expect(wrapper.find('[data-testid="corpus-applied"]').exists()).toBe(false)
  })

  it('disables the library filter when the corpus does not record libraries', async () => {
    const wrapper = await loadedPage()

    // Quasar puts the test id on the field's inner element.
    const libraries = wrapper.get('[data-testid="filter-libraries"]').element.closest('.q-field')!
    expect(libraries.classList.contains('q-field--disabled')).toBe(true)
    expect(libraries.textContent).toContain('does not record libraries')
  })

  it('applies the filters and shows the matching documents with their filters', async () => {
    const wrapper = await loadedPage()
    await wrapper.get('[data-testid="filter-year-min"]').setValue('1900')
    await wrapper.get('[data-testid="filter-year-max"]').setValue('1920')
    await wrapper.get('[data-testid="filter-title"]').setValue('  Pražský: věstník ')
    await wrapper.get('form').trigger('submit')
    await flush()

    expect(requests[1].body).toEqual({ filters: { year_min: 1900, year_max: 1920, title_contains: 'Pražský: věstník' } })
    expect(wrapper.text()).toContain('Counting the matching documents')
    requests[1].answer(overviewBody({ filters: filtered, total_documents: 4 }))
    await flushPromises()

    expect(wrapper.text()).not.toContain('Counting the matching documents')
    expect(wrapper.text()).toContain('Matching documents')
    expect(wrapper.get('[data-testid="corpus-total"]').text()).toBe('4')
    expect(wrapper.get('[data-testid="corpus-of-total"]').text()).toBe('of 10 documents in the corpus')
    // The filters of the counts shown, as the server applied them.
    expect(wrapper.get('[data-testid="corpus-applied"]').findAll('.q-chip').map(c => c.text())).toEqual([
      expect.stringContaining('Years: 1900–1920'), expect.stringContaining('Title: Pražský věstník'),
      expect.stringContaining('Language: Czech (ces)')
    ])
  })

  it('removes one filter from its chip and all of them with Clear all', async () => {
    const wrapper = await loadedPage()
    await wrapper.get('form').trigger('submit')
    await flush()
    requests[1].answer(overviewBody({ filters: filtered, total_documents: 4 }))
    await flushPromises()

    await wrapper.get('[data-testid="corpus-applied"] .q-chip .q-chip__icon--remove').trigger('click')
    await flush()
    expect(requests[2].body).toEqual({ filters: { title_contains: 'Pražský věstník', libraries: [], languages: ['ces'] } })
    requests[2].answer(overviewBody({ filters: { ...filtered, year_min: null, year_max: null }, total_documents: 5 }))
    await flushPromises()
    // The form shows the filters requested now.
    expect((wrapper.get('[data-testid="filter-year-min"]').element as HTMLInputElement).value).toBe('')
    expect((wrapper.get('[data-testid="filter-title"]').element as HTMLInputElement).value).toBe('Pražský věstník')

    await wrapper.get('[data-testid="corpus-clear-all"]').trigger('click')
    await flush()
    expect(requests[3].body).toEqual({ filters: {} })
    requests[3].answer(overviewBody())
    await flushPromises()
    expect(wrapper.text()).toContain('Documents in the corpus')
    expect(wrapper.find('[data-testid="corpus-applied"]').exists()).toBe(false)
  })

  it('tells no matching documents apart from an empty corpus', async () => {
    const wrapper = await loadedPage()
    await wrapper.get('form').trigger('submit')
    await flush()
    requests[1].answer(overviewBody({
      filters: { ...NO_FILTERS, title_contains: 'zzz' },
      total_documents: 0,
      publication_year: { available: true, years: [], unknown_count: 0 },
      languages: { available: true, values: [], other_count: 0, unknown_count: 0 }
    }))
    await flushPromises()

    expect(wrapper.get('[data-testid="corpus-no-match"]').text()).toContain('No documents match these filters')
    expect(wrapper.find('[data-testid="corpus-empty"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="corpus-of-total"]').text()).toBe('of 10 documents in the corpus')
  })

  it('shows a refused filter without Retry and keeps the filters editable', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const wrapper = await loadedPage()
    await wrapper.get('[data-testid="filter-title"]').setValue('a')
    await wrapper.get('form').trigger('submit')
    await flush()
    requests[1].answer({ detail: [{ loc: ['body', 'filters', 'title_contains'], msg: 'Enter at least one title word of two or more letters or digits.' }] }, 422)
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Enter at least one title word')
    expect(button(wrapper, 'Retry')).toBeUndefined()
    expect(wrapper.find('[data-testid="corpus-total"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="corpus-filters"]').exists()).toBe(true)
    expect((wrapper.get('[data-testid="filter-title"]').element as HTMLInputElement).value).toBe('a')
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
    expect(state.distributions.value?.totalDocuments).toBe(12)
    expect(state.loading.value).toBe(false)

    const third = state.load()
    await flush()
    scope.stop()
    expect(requests[2].signal?.aborted).toBe(true)
    await third
  })
})
