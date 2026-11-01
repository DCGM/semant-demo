import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { Quasar } from 'quasar'
import { effectScope, nextTick } from 'vue'

import { categoryBarSpec, categoryRows, coverage, filterGroups, isUnfiltered, languageLabel, libraryLabel, withoutFilter } from 'src/features/analytics/corpusOverview'
import CorpusOverviewPage from 'src/features/analytics/CorpusOverviewPage.vue'
import PublicationTimeline from 'src/features/analytics/PublicationTimeline.vue'
import { SLOW_AFTER_MS, useCorpusOverview } from 'src/features/analytics/useCorpusOverview'
import VegaChart from 'src/shared/visualization/VegaChart.vue'
import { loadEmbed } from 'src/shared/visualization/loadEmbed'

vi.mock('src/shared/visualization/loadEmbed', () => ({ loadEmbed: vi.fn() }))

type SignalHandler = (name: string, value: unknown) => void

/**
 * Drawings made through the mocked vega-embed; `fail` makes the next ones fail. With `held`,
 * a drawing finishes only when its `finish` is called, so drawings can finish in any order.
 * `signals` holds the signal listeners of each drawing, so a test can play an interaction.
 */
const embedded = {
  calls: [] as {
    element: HTMLElement, spec: Record<string, unknown>, options: unknown,
    finalize: ReturnType<typeof vi.fn>, finish: () => void, signals: Map<string, SignalHandler>
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
    const signals = new Map<string, SignalHandler>()
    let finish = () => undefined as void
    const finished = new Promise<void>((resolve) => { finish = resolve })
    embedded.calls.push({ element: el, spec: spec as Record<string, unknown>, options, finalize, finish, signals })
    if (embedded.held) await finished
    // vega-embed clears and fills the element it is given.
    el.innerHTML = `<svg data-mark="${String((spec as { mark?: unknown }).mark)}"></svg>`
    const view = {
      addSignalListener (name: string, handler: SignalHandler) {
        signals.set(name, handler)
        return view
      }
    }
    return { finalize, view }
  })
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

const NO_FILTERS = { year_min: null, year_max: null, title_contains: [], libraries: [], languages: [] }
const LIBRARIES = { available: true, values: [{ value: 'mzk', count: 6 }, { value: 'nkp', count: 1 }], other_count: 0, unknown_count: 3 }

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

  it('groups the applied filters by kind and removes one value at a time', () => {
    const filters = { yearMin: 1900, yearMax: 1920, titleContains: ['brno', 'Pražský věstník'], libraries: ['mzk', 'svkhk'], languages: ['ces'] }
    expect(filterGroups(filters).map(g => [g.label, g.chips.map(c => c.label)])).toEqual([
      ['Years', ['1900–1920']], ['Title contains', ['brno', 'Pražský věstník']],
      ['Library', ['Moravian Library (mzk)', 'svkhk']], ['Language', ['Czech (ces)']]
    ])
    expect(filterGroups({ yearMin: 1909 })[0].chips[0].label).toBe('from 1909')
    expect(filterGroups({ yearMax: 1909 })[0].chips[0].label).toBe('until 1909')
    expect(filterGroups({ yearMin: 1909, yearMax: 1909 })[0].chips[0].label).toBe('1909')
    expect(withoutFilter(filters, 'title', 'brno').titleContains).toEqual(['Pražský věstník'])
    expect(withoutFilter(filters, 'libraries', 'mzk').libraries).toEqual(['svkhk'])
    const withoutYears = withoutFilter(filters, 'years')
    expect([withoutYears.yearMin, withoutYears.yearMax]).toEqual([undefined, undefined])
    expect(isUnfiltered({ yearMin: null, yearMax: null, titleContains: [], libraries: [], languages: [] })).toBe(true)
    expect(isUnfiltered(withoutFilter({ languages: ['ces'] }, 'languages', 'ces'))).toBe(true)
  })

  it('computes coverage, also of an empty corpus', () => {
    expect(coverage(3, 10)).toEqual({ known: 7, unknown: 3, percent: 70 })
    expect(coverage(0, 0)).toEqual({ known: 0, unknown: 0, percent: 0 })
  })

  it('titles the chart axes and tooltips in documents', () => {
    const bars = JSON.stringify(categoryBarSpec(categoryRows({ available: true, values: [], otherCount: 0, unknownCount: 1 }, String), 'Language'))
    expect(bars).toContain('"title":"Documents"')
    expect(bars).not.toMatch(/chunk|hit/i)
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

  it('reports the named signals of the shown drawing', async () => {
    const wrapper = mount(VegaChart, { props: { spec: { mark: 'bar' }, label: 'Chart', signals: ['period'] } })
    await flush()

    embedded.calls[0].signals.get('period')?.('period', { start: [1900, 1910] })
    expect(wrapper.emitted('signal')).toEqual([['period', { start: [1900, 1910] }]])
    expect([...embedded.calls[0].signals.keys()]).toEqual(['period'])
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
  type Request = { url: string, signal?: AbortSignal | null, body: unknown, answer: (body: unknown, status?: number) => void }
  /** Requests of the distributions; `heatmapRequests`: of the library × year counts. */
  let requests: Request[]
  let heatmapRequests: Request[]

  beforeEach(() => {
    resetEmbed()
    requests = []
    heatmapRequests = []
    globalThis.fetch = vi.fn((input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => new Promise<Response>((resolve, reject) => {
      const url = String(input)
      init?.signal?.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })))
      const request = {
        url,
        signal: init?.signal,
        body: JSON.parse(String(init?.body)),
        answer: (body: unknown, status = 200) => resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
      }
      if (url.includes('/api/analytics/corpus/library-years')) heatmapRequests.push(request)
      else {
        expect(url).toContain('/api/analytics/corpus/distributions')
        requests.push(request)
      }
    })) as typeof fetch
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  const mountPage = () => mount(CorpusOverviewPage, { global: { plugins: [[Quasar, {}]] } })
  type Page = ReturnType<typeof mountPage>

  /** The mounted page once its request has been sent (the client sends it asynchronously). */
  async function openPage () {
    const wrapper = mountPage()
    await flush()
    return wrapper
  }

  /** The page with its whole-corpus counts loaded (filter choices from `changes`). */
  async function loadedPage (changes: Record<string, unknown> = {}) {
    const wrapper = await openPage()
    requests[0].answer(overviewBody(changes))
    await flushPromises()
    await flush()
    return wrapper
  }

  /** Answers the last distributions request and lets the page draw. */
  async function answer (body: unknown, status = 200) {
    requests[requests.length - 1].answer(body, status)
    await flushPromises()
    await flush()
  }

  const tableText = (wrapper: Page, testId: string) =>
    wrapper.get(`[data-testid="${testId}"]`).findAll('tbody tr').map(r => r.findAll('th, td').map(c => c.text()))
  const button = (wrapper: Page, text: string) => wrapper.findAll('button').find(b => b.text().includes(text))
  const input = (wrapper: Page, testId: string) => wrapper.get(`[data-testid="${testId}"]`).element as HTMLInputElement
  const applied = (wrapper: Page, key: string) =>
    wrapper.get(`[data-testid="corpus-applied-${key}"]`).findAll('.q-chip').map(c => c.text().replace(/cancel$/, '').trim())

  async function submit (wrapper: Page) {
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await flush()
  }

  it('states its scope and shows totals, coverage, charts and tables in documents', async () => {
    const wrapper = await openPage()
    expect(wrapper.text()).toContain('Loading the corpus overview')
    expect(wrapper.get('[data-testid="corpus-scope"]').text()).toMatch(/searchable semANT corpus.*not your collections/s)

    await answer(overviewBody())

    expect(wrapper.get('[data-testid="corpus-total"]').text()).toBe('10')
    // The corpus is effectively static: no refresh control.
    expect(wrapper.findAll('button').map(b => b.text())).not.toContain(expect.stringContaining('Reload'))
    const years = wrapper.get('[data-testid="corpus-years"]')
    expect(years.text()).toContain('7 of 10 documents (70 %) have a publication year; 3 unknown.')
    // The main range 1900–1919 in single years; long empty periods as one row.
    expect(tableText(wrapper, 'corpus-years')).toEqual([
      ['1900–1904 — no documents (5 years)', '0'], ['1905', '4'], ['1906–1909 — no documents (4 years)', '0'],
      ['1910', '2'], ['1911–1918 — no documents (8 years)', '0'], ['1919', '1'], ['Unknown or invalid year', '3']
    ])
    const languages = wrapper.get('[data-testid="corpus-languages"]')
    expect(languages.text()).toContain('8 of 10 documents (80 %) have a language; 2 unknown.')
    expect(tableText(wrapper, 'corpus-languages')).toEqual([
      ['Czech (ces)', 'ces', '5'], ['Czech (cze)', 'cze', '2'], ['Other values', '—', '1'], ['Unknown', '—', '2']
    ])
    // Two charts: years and languages; the library is unavailable, and so is the heatmap.
    expect(wrapper.findAll('.vega-chart__canvas').map(c => c.attributes('aria-label'))).toEqual([
      expect.stringContaining('documents per year from 1900–1919'), expect.stringContaining('per language')
    ])
    expect(wrapper.get('[data-testid="corpus-heatmap"]').text()).toContain('Not available')
  })

  it('shows an unavailable property as unavailable, not as zero', async () => {
    const wrapper = await loadedPage()

    const libraries = wrapper.get('[data-testid="corpus-libraries"]')
    expect(libraries.text()).toContain('Not available')
    expect(libraries.text()).toContain('not a count of zero')
    expect(libraries.find('table').exists()).toBe(false)
  })

  it('shows an empty corpus without charts', async () => {
    const wrapper = await loadedPage({
      total_documents: 0,
      publication_year: { available: true, years: [], unknown_count: 0 },
      languages: { available: true, values: [], other_count: 0, unknown_count: 0 }
    })

    expect(wrapper.get('[data-testid="corpus-total"]').text()).toBe('0')
    expect(wrapper.get('[data-testid="corpus-empty"]').text()).toContain('no documents')
    expect(embedded.calls).toHaveLength(0)
  })

  it('reports a failure with Retry, which loads the overview again', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const wrapper = await openPage()
    await answer({ detail: 'Internal Server Error' }, 500)

    expect(wrapper.get('[role="alert"]').text()).toContain('Internal Server Error')
    expect(wrapper.find('[data-testid="corpus-total"]').exists()).toBe(false)

    await button(wrapper, 'Retry')!.trigger('click')
    await flush()
    expect(requests).toHaveLength(2)
    await answer(overviewBody())
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

  it('sends no filters first and offers the whole corpus as filter choices', async () => {
    const wrapper = await loadedPage({ libraries: LIBRARIES })

    expect(requests[0].body).toEqual({ filters: {} })
    const panel = wrapper.get('[data-testid="corpus-filters"]')
    expect(panel.text()).toContain('ignores case, not diacritics (skola ≠ škola)')
    expect(panel.text()).toContain('matches language values by word, ignoring case')
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

  it('applies the years and adds a title, emptying the title field', async () => {
    const wrapper = await loadedPage()
    await wrapper.get('[data-testid="filter-year-min"]').setValue('1900')
    await wrapper.get('[data-testid="filter-year-max"]').setValue('1920')
    await wrapper.get('[data-testid="filter-title"]').setValue('  Pražský: věstník ')
    await submit(wrapper)

    expect(requests[1].body).toEqual({ filters: { year_min: 1900, year_max: 1920, title_contains: ['Pražský: věstník'], libraries: [], languages: [] } })
    expect(input(wrapper, 'filter-title').value).toBe('')
    expect(input(wrapper, 'filter-year-min').value).toBe('1900')
    expect(wrapper.text()).toContain('Counting the matching documents')
    await answer(overviewBody({ filters: { ...NO_FILTERS, year_min: 1900, year_max: 1920, title_contains: ['Pražský věstník'] }, total_documents: 4 }))

    expect(wrapper.text()).not.toContain('Counting the matching documents')
    expect(wrapper.text()).toContain('Matching documents')
    expect(wrapper.get('[data-testid="corpus-total"]').text()).toBe('4')
    expect(wrapper.get('[data-testid="corpus-of-total"]').text()).toBe('of 10 documents in the corpus')
    // The filters of the counts shown, as the server applied them.
    expect(applied(wrapper, 'years')).toEqual(['1900–1920'])
    expect(applied(wrapper, 'title')).toEqual(['Pražský věstník'])
  })

  it('adds another title as an alternative and removes one of them from its chip', async () => {
    const wrapper = await loadedPage()
    await wrapper.get('[data-testid="filter-title"]').setValue('brno')
    await submit(wrapper)
    await answer(overviewBody({ filters: { ...NO_FILTERS, title_contains: ['brno'] }, total_documents: 3 }))
    await wrapper.get('[data-testid="filter-title"]').setValue('brna')
    await submit(wrapper)

    expect(requests[2].body).toEqual({ filters: { title_contains: ['brno', 'brna'], libraries: [], languages: [] } })
    await answer(overviewBody({ filters: { ...NO_FILTERS, title_contains: ['brna', 'brno'] }, total_documents: 5 }))
    expect(applied(wrapper, 'title')).toEqual(['brna', 'brno'])
    expect(wrapper.get('[data-testid="corpus-applied-title"]').text()).toContain('or')

    await wrapper.get('[data-testid="corpus-applied-title"] .q-chip .q-chip__icon--remove').trigger('click')
    await flush()
    expect(requests[3].body).toEqual({ filters: { title_contains: ['brno'], libraries: [], languages: [] } })
  })

  const removeChip = async (wrapper: Page, key: string, index: number) => {
    await wrapper.get(`[data-testid="corpus-applied-${key}"]`).findAll('.q-chip .q-chip__icon--remove')[index]!.trigger('click')
    await flush()
  }

  it('removes chips one after another while the first removal is still being counted', async () => {
    const wrapper = await loadedPage()
    await wrapper.get('[data-testid="filter-title"]').setValue('brno')
    await submit(wrapper)
    await wrapper.get('[data-testid="filter-title"]').setValue('praha')
    await submit(wrapper)
    await answer(overviewBody({ filters: { ...NO_FILTERS, title_contains: ['brno', 'praha'] }, total_documents: 5 }))

    await removeChip(wrapper, 'title', 0)
    expect(requests[3].body).toEqual({ filters: { title_contains: ['praha'], libraries: [], languages: [] } })
    // The chips still show the counted filters; the second removal is built on the requested ones,
    // so the title removed first does not come back.
    await removeChip(wrapper, 'title', 1)
    expect(requests[4].body).toEqual({ filters: { title_contains: [], libraries: [], languages: [] } })
  })

  it('removes a title from its chip as the server echoed it, also when typed otherwise', async () => {
    const wrapper = await loadedPage()
    await wrapper.get('[data-testid="filter-title"]').setValue('Dopisy, z Prahy')
    await submit(wrapper)
    expect(requests[1].body).toEqual({ filters: { title_contains: ['Dopisy, z Prahy'], libraries: [], languages: [] } })
    await answer(overviewBody({ filters: { ...NO_FILTERS, title_contains: ['Dopisy Prahy'] }, total_documents: 1 }))
    expect(applied(wrapper, 'title')).toEqual(['Dopisy Prahy'])

    await removeChip(wrapper, 'title', 0)
    expect(requests[2].body).toEqual({ filters: { title_contains: [], libraries: [], languages: [] } })
  })

  it('keeps typed years that are not applied when an answer arrives', async () => {
    const wrapper = await loadedPage()
    await wrapper.get('[data-testid="filter-title"]').setValue('brno')
    await submit(wrapper)
    await wrapper.get('[data-testid="filter-year-min"]').setValue('1900')
    await answer(overviewBody({ filters: { ...NO_FILTERS, title_contains: ['brno'] }, total_documents: 3 }))
    expect(input(wrapper, 'filter-year-min').value).toBe('1900')

    // Clearing every filter still empties them, from the chips and from the form.
    await wrapper.get('[data-testid="corpus-clear-all"]').trigger('click')
    await flush()
    expect(input(wrapper, 'filter-year-min').value).toBe('')
    await answer(overviewBody())
    await wrapper.get('[data-testid="filter-year-max"]').setValue('1910')
    await wrapper.get('[data-testid="filter-clear"]').trigger('click')
    await flush()
    expect(input(wrapper, 'filter-year-max').value).toBe('')
  })

  it('applies a library as soon as it is chosen or unchosen, keeping what is typed', async () => {
    const wrapper = await loadedPage({ libraries: LIBRARIES })
    await wrapper.get('[data-testid="filter-title"]').setValue('brno')
    const [libraries] = wrapper.findAllComponents({ name: 'QSelect' })

    // The select keeps no value of its own; a click reports the option clicked.
    libraries.vm.$emit('update:model-value', ['mzk'])
    await flush()
    expect(requests[1].body).toEqual({ filters: { title_contains: [], libraries: ['mzk'], languages: [] } })
    await answer(overviewBody({ libraries: LIBRARIES, filters: { ...NO_FILTERS, libraries: ['mzk'] }, total_documents: 6 }))
    expect(applied(wrapper, 'libraries')).toEqual(['Moravian Library (mzk)'])
    expect(libraries.props('modelValue')).toEqual([])
    expect(input(wrapper, 'filter-title').value).toBe('brno')

    libraries.vm.$emit('update:model-value', ['nkp'])
    await flush()
    expect(requests[2].body).toEqual({ filters: { title_contains: [], libraries: ['mzk', 'nkp'], languages: [] } })
    // Unchosen: built on the filters requested last (mzk and nkp).
    libraries.vm.$emit('update:model-value', ['mzk'])
    await flush()
    expect(requests[3].body).toEqual({ filters: { title_contains: [], libraries: ['nkp'], languages: [] } })
  })

  it('clears every filter with Clear all', async () => {
    const wrapper = await loadedPage()
    await wrapper.get('[data-testid="filter-year-min"]').setValue('1900')
    await submit(wrapper)
    await answer(overviewBody({ filters: { ...NO_FILTERS, year_min: 1900 }, total_documents: 7 }))

    await wrapper.get('[data-testid="corpus-clear-all"]').trigger('click')
    await flush()
    expect(requests[2].body).toEqual({ filters: {} })
    await answer(overviewBody())
    expect(wrapper.text()).toContain('Documents in the corpus')
    expect(wrapper.find('[data-testid="corpus-applied"]').exists()).toBe(false)
    expect(input(wrapper, 'filter-year-min').value).toBe('')
  })

  it('tells no matching documents apart from an empty corpus', async () => {
    const wrapper = await loadedPage()
    await wrapper.get('[data-testid="filter-title"]').setValue('zzz')
    await submit(wrapper)
    await answer(overviewBody({
      filters: { ...NO_FILTERS, title_contains: ['zzz'] },
      total_documents: 0,
      publication_year: { available: true, years: [], unknown_count: 0 },
      languages: { available: true, values: [], other_count: 0, unknown_count: 0 }
    }))

    expect(wrapper.get('[data-testid="corpus-no-match"]').text()).toContain('No documents match these filters')
    expect(wrapper.find('[data-testid="corpus-empty"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="corpus-of-total"]').text()).toBe('of 10 documents in the corpus')
  })

  it.each([
    ['filter-year-min', '19x0', 'Enter a whole year'],
    ['filter-year-max', String(new Date().getFullYear() + 1), `At most ${new Date().getFullYear()}`],
    ['filter-title', 'a v', 'Enter at least one word of two or more'],
    ['filter-title', 'škol*', 'Wildcards (* or ?) are not supported']
  ])('checks %s = %s before anything is sent', async (field, value, message) => {
    const wrapper = await loadedPage()
    await wrapper.get(`[data-testid="${field}"]`).setValue(value)
    await submit(wrapper)

    expect(requests).toHaveLength(1)
    expect(wrapper.get('[data-testid="corpus-filters"]').text()).toContain(message)
    expect(input(wrapper, field).value).toBe(value)
  })

  it('shows a filter the server refuses without Retry and keeps the filters editable', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const wrapper = await loadedPage()
    await wrapper.get('[data-testid="filter-title"]').setValue('brno')
    await submit(wrapper)
    await answer({ detail: [{ loc: ['body', 'filters', 'title_contains', 0], msg: 'The title filter takes at most 5 words.' }] }, 422)

    expect(wrapper.get('[role="alert"]').text()).toContain('at most 5 words')
    expect(button(wrapper, 'Retry')).toBeUndefined()
    expect(wrapper.find('[data-testid="corpus-total"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="corpus-filters"]').exists()).toBe(true)
  })

  it('applies the period shown in the timeline as a year filter, keeping the other filters', async () => {
    const wrapper = await loadedPage()
    await wrapper.get('[data-testid="filter-title"]').setValue('brno')
    await submit(wrapper)
    await answer(overviewBody({ filters: { ...NO_FILTERS, title_contains: ['brno'] } }))

    await wrapper.get('[data-testid="timeline-apply-period"]').trigger('click')
    await flush()
    expect(requests[2].body).toEqual({ filters: { year_min: 1900, year_max: 1919, title_contains: ['brno'], libraries: [], languages: [] } })
  })

  it('applies the period shown in the timeline keeping a title still being counted', async () => {
    const wrapper = await loadedPage()
    await wrapper.get('[data-testid="filter-title"]').setValue('brno')
    await submit(wrapper)

    await wrapper.get('[data-testid="timeline-apply-period"]').trigger('click')
    await flush()
    expect(requests[2].body).toEqual({ filters: { year_min: 1900, year_max: 1919, title_contains: ['brno'], libraries: [], languages: [] } })
  })

  it('counts the library × period heatmap only when asked, and again only for other filters', async () => {
    const wrapper = await loadedPage({ libraries: LIBRARIES })
    expect(heatmapRequests).toHaveLength(0)

    await button(wrapper, 'Show documents per library and period')!.trigger('click')
    await flush()
    // The filters of the counts shown (the whole corpus).
    expect(heatmapRequests.map(r => r.body)).toEqual([{ filters: { title_contains: [], libraries: [], languages: [] } }])
    heatmapRequests[0].answer({
      scope: 'searchable_corpus',
      unit: 'documents',
      filters: NO_FILTERS,
      total_documents: 10,
      computed_at: '2026-10-15T12:00:00Z',
      available: true,
      rows: [
        { library: 'mzk', kind: 'value', total_documents: 6, years: [{ year: 1905, count: 4 }, { year: 1910, count: 2 }], unknown_year_count: 0 },
        { library: null, kind: 'unknown', total_documents: 4, years: [{ year: 1919, count: 1 }], unknown_year_count: 3 }
      ]
    })
    await flushPromises()
    await flush()

    const heatmap = wrapper.get('[data-testid="heatmap"]')
    expect(heatmap.get('[data-testid="heatmap-note"]').text()).toContain('1900–1919 in single years')
    expect(tableText(wrapper, 'heatmap')).toEqual([
      ['1900–1904 — no documents (5 years)', '0', '0', '0'], ['1905', '4', '0', '4'],
      ['1906–1909 — no documents (4 years)', '0', '0', '0'], ['1910', '2', '0', '2'],
      ['1911–1918 — no documents (8 years)', '0', '0', '0'], ['1919', '0', '1', '1'],
      ['Outside 1900–1919', '0', '0', '0'], ['Unknown or invalid year', '0', '3', '3'], ['All documents', '6', '4', '10']
    ])

    // Zooming the timeline changes the heatmap's periods without counting again.
    await wrapper.get('[data-testid="timeline-zoom-in"]').trigger('click')
    await flush()
    expect(heatmap.get('[data-testid="heatmap-note"]').text()).toContain('1905–1914 in single years')
    expect(heatmapRequests).toHaveLength(1)

    // Other filters: counted again, for the same documents as the page.
    await wrapper.get('[data-testid="filter-title"]').setValue('brno')
    await submit(wrapper)
    await answer(overviewBody({ libraries: LIBRARIES, filters: { ...NO_FILTERS, title_contains: ['brno'] } }))
    expect(heatmapRequests).toHaveLength(2)
    expect(heatmapRequests[1].body).toEqual({ filters: { title_contains: ['brno'], libraries: [], languages: [] } })
  })

  it('ignores the answer of a request replaced by a newer one and marks a refused request', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
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

    const refused = state.load({ titleContains: ['x'] })
    await flush()
    requests[2].answer({ detail: 'invalid' }, 422)
    await refused
    expect([state.invalid.value, state.distributions.value]).toEqual([true, null])
    // The whole-corpus counts stay for the filter choices.
    expect(state.corpus.value?.totalDocuments).toBe(12)

    const third = state.load()
    await flush()
    scope.stop()
    expect(requests[3].signal?.aborted).toBe(true)
    await third
  })
})

describe('PublicationTimeline', () => {
  beforeEach(resetEmbed)

  const YEARS = [
    { year: 311, count: 1 }, { year: 1600, count: 2 }, { year: 1690, count: 3 }, { year: 1785, count: 1 },
    { year: 2000, count: 1 }
  ]
  const mountTimeline = () => mount(PublicationTimeline, {
    props: { distribution: { available: true, years: YEARS, unknownCount: 2 } },
    global: { plugins: [[Quasar, {}]] }
  })
  const windowText = (wrapper: VueWrapper) => wrapper.get('[data-testid="timeline-window"]').text()
  const click = async (wrapper: VueWrapper, testId: string) => {
    await wrapper.get(`[data-testid="${testId}"]`).trigger('click')
    await flush()
  }

  it('opens on the main range and names the documents outside it', async () => {
    const wrapper = mountTimeline()
    await flush()

    expect(windowText(wrapper)).toBe('1600–1789 · bins of 5 years')
    expect(wrapper.get('[data-testid="timeline-outside"]').text())
      .toContain('Not shown: 1 document before 1600 (year 311); 1 document after 1789 (year 2000).')
    expect(wrapper.get('[data-testid="timeline-reset"]').attributes('disabled')).toBeDefined()
    expect(wrapper.emitted('view')?.at(-1)).toEqual([{ window: { start: 1600, end: 1789 }, width: 5 }])
  })

  it('zooms, shows the full range and resets to the main range without changing the counts', async () => {
    const wrapper = mountTimeline()
    await flush()

    await click(wrapper, 'timeline-zoom-in')
    expect(windowText(wrapper)).toBe('1645–1744 · bins of 5 years')
    await click(wrapper, 'timeline-full')
    expect(windowText(wrapper)).toBe('300–2049 · bins of 50 years')
    expect(wrapper.find('[data-testid="timeline-outside"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="timeline-zoom-out"]').attributes('disabled')).toBeDefined()
    await click(wrapper, 'timeline-reset')
    expect(windowText(wrapper)).toBe('1600–1789 · bins of 5 years')
    expect(wrapper.emitted('applyPeriod')).toBeUndefined()
  })

  it('zooms to a period dragged across the chart when the drag ends', async () => {
    const wrapper = mountTimeline()
    await flush()

    const drawing = embedded.calls[embedded.calls.length - 1]
    drawing.signals.get('period')?.('period', { start: [1690.3, 1700.6] })
    expect(windowText(wrapper)).toBe('1600–1789 · bins of 5 years')
    await wrapper.get('.vega-chart').trigger('pointerup')
    await flush()
    expect(windowText(wrapper)).toBe('1690–1700 · single years')
  })

  it('applies the shown period, at most up to the current year', async () => {
    const wrapper = mountTimeline()
    await flush()

    await click(wrapper, 'timeline-apply-period')
    await click(wrapper, 'timeline-full')
    await click(wrapper, 'timeline-apply-period')
    expect(wrapper.emitted('applyPeriod')).toEqual([
      [{ start: 1600, end: 1789 }], [{ start: 300, end: new Date().getFullYear() }]
    ])
  })
})
