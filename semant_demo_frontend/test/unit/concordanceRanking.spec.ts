import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { QBtn, QCheckbox, QChip, QInput, QSelect, Quasar } from 'quasar'

import { RetrievalMode, SpanType, TextScope, type AnnotationListRow } from 'src/generated/api'
import ConcordanceFilterChips from 'src/features/annotations/concordance/ConcordanceFilterChips.vue'
import ConcordanceTable from 'src/features/annotations/concordance/ConcordanceTable.vue'
import ConcordanceToolbar from 'src/features/annotations/concordance/ConcordanceToolbar.vue'
import SelectionBar from 'src/features/annotations/concordance/SelectionBar.vue'
import {
  clearSimilar, defaultFilters, similarChange, useConcordanceStore, withMode, type ConcordanceFilters
} from 'src/features/annotations/concordance/concordanceStore'
import { concordanceChips, rankedLabel, similarityHintText, unsortableLabel } from 'src/features/annotations/concordance/filterChips'
import { useAnnotationSelectionStore } from 'src/features/annotations/annotationSelectionStore'

// Ranked annotation retrieval in the workspace (#664): the mode, k and source are sent with
// the query, the page says it is a top k with its vector coverage, Find similar keeps the
// other filters with the source as a reference chip, and "select all" takes the top k only.

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

const row = (id: string, text = id): AnnotationListRow => ({
  id,
  tagId: 't1',
  type: SpanType.pos,
  chunkId: 'c1',
  documentId: 'd1',
  start: 0,
  end: text.length,
  revision: 1,
  textStatus: 'ready',
  text,
  leftContext: 'left ',
  rightContext: ' right',
  documentAvailable: true,
  documentTitle: 'Kronika',
  documentYear: 1851
} as AnnotationListRow)

const topK = (ids: string[], extra: Record<string, unknown> = {}) => ({
  rows: ids.map(id => row(id)),
  total: ids.length,
  offset: 0,
  limit: 50,
  result: { kind: 'top_k', mode: 'semantic', k: 100, truncated: false, coverage: { matching: 40, with_vector: 3 }, ...extra }
})

function controlledFetch () {
  const calls: { url: URL, body: unknown, answer: (body: unknown, status?: number) => void }[] = []
  const fetchMock = vi.fn((input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => new Promise<Response>((resolve, reject) => {
    const abort = () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' }))
    if (init?.signal?.aborted) abort()
    init?.signal?.addEventListener('abort', abort)
    calls.push({
      url: new URL(String(input)),
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : undefined,
      answer: (body, status = 200) => resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
    })
  }))
  return { calls, fetchMock }
}

function filters (change: Partial<ConcordanceFilters>): ConcordanceFilters {
  return { ...defaultFilters(), ...change }
}

describe('ranked queries of the concordance store', () => {
  const originalFetch = globalThis.fetch
  let calls: ReturnType<typeof controlledFetch>['calls']
  const rowCalls = () => calls.filter(c => c.url.pathname.endsWith('/annotations'))
  const idCalls = () => calls.filter(c => c.url.pathname.endsWith('/annotations/ids'))
  const last = () => rowCalls()[rowCalls().length - 1]

  beforeEach(() => {
    setActivePinia(createPinia())
    const controlled = controlledFetch()
    calls = controlled.calls
    globalThis.fetch = controlled.fetchMock as typeof fetch
  })
  afterEach(() => { globalThis.fetch = originalFetch })

  async function opened () {
    const store = useConcordanceStore()
    const opening = store.open('col-1')
    await flush()
    rowCalls()[0].answer({ rows: [row('a'), row('b')], total: 2, offset: 0, limit: 50 })
    calls.filter(c => c.url.pathname.endsWith('/documents')).forEach(c => c.answer([]))
    await opening
    return store
  }

  it('keeps the words a filter and ranks by the separate similarity text, without a sort', async () => {
    const store = await opened()
    const ranking = store.setFilters({ text: ' novak ', similarity: ' hejtman ', textScope: TextScope.both })
    await flush()
    const params = last().url.searchParams
    expect(Object.fromEntries(['mode', 'k', 'q', 'ranking_query', 'sort', 'text_scope', 'similar_to'].map(k => [k, params.get(k)])))
      .toEqual({ mode: 'hybrid', k: '100', q: 'novak', ranking_query: 'hejtman', sort: null, text_scope: 'both', similar_to: null })
    last().answer(topK(['n1', 'n2'], { mode: 'hybrid' }))
    await ranking
    expect(store.rows.map(r => r.id)).toEqual(['n1', 'n2'])
    expect(store.page?.result?.coverage).toEqual({ matching: 40, withVector: 3 })

    // Emptying either input leaves the other: words alone are a complete lexical result.
    void store.setFilters({ similarity: '' })
    await flush()
    expect([last().url.searchParams.get('mode'), last().url.searchParams.get('ranking_query'), last().url.searchParams.get('q'),
      last().url.searchParams.get('sort')]).toEqual([null, null, 'novak', 'document'])
  })

  it('ranks by the similarity text alone without a words filter, and browses with neither', async () => {
    const store = await opened()
    void store.setFilters({ similarity: 'hejtman' })
    await flush()
    expect([store.filters.mode, last().url.searchParams.get('q'), last().url.searchParams.get('text_scope'),
      last().url.searchParams.get('ranking_query')]).toEqual([RetrievalMode.hybrid, null, null, 'hejtman'])
    void store.setFilters({ similarity: '   ' })
    await flush()
    expect([store.filters.mode, last().url.searchParams.get('mode'), last().url.searchParams.get('ranking_query')])
      .toEqual([RetrievalMode.lexical, null, null])
  })

  it('finds similar annotations within the filters, replacing a similarity text instead of reusing it', async () => {
    const store = await opened()
    const filtering = store.setFilters({ tagIds: ['t1'], text: 'praha' })
    await flush()
    last().answer({ rows: [], total: 0, offset: 0, limit: 50 })
    calls.filter(c => c.url.pathname.endsWith('/documents')).forEach(c => c.answer([]))
    await filtering
    const source = row('a', 'Praha')

    void store.findSimilar(source)
    await flush()
    let params = last().url.searchParams
    expect([params.get('mode'), params.get('similar_to'), params.get('q'), params.get('ranking_query'), params.getAll('tag_id'),
      params.get('include_source')]).toEqual(['similar', 'a', 'praha', null, ['t1'], null])

    void store.setFilters({ includeSource: true })
    await flush()
    expect(last().url.searchParams.get('include_source')).toBe('true')

    // A similarity text and a source exclude each other; the text is never turned into the source query.
    expect(similarChange(source)).toEqual({ similarTo: source, includeSource: false, similarity: '' })
    void store.setFilters({ similarity: 'hejtman' })
    await flush()
    params = last().url.searchParams
    expect([store.filters.similarTo, params.get('mode'), params.get('similar_to'), params.get('ranking_query'),
      params.get('include_source')]).toEqual([null, 'hybrid', null, 'hejtman', null])

    void store.setFilters(clearSimilar())
    void store.setFilters({ similarity: '' })
    await flush()
    params = last().url.searchParams
    expect([params.get('mode'), params.get('similar_to'), params.get('sort')]).toEqual([null, null, 'document'])
  })

  it('shows why a ranked query was refused: no source vector, no embedding service', async () => {
    const store = await opened()
    const refused = store.findSimilar(row('a'))
    await flush()
    last().answer({ detail: 'This annotation has no current vector yet.' }, 400)
    await refused
    expect(store.error).toBe('This annotation has no current vector yet.')

    const unavailable = store.setFilters({ similarity: 'x' })
    await flush()
    last().answer({ detail: 'The embedding service is unavailable.' }, 503)
    await unavailable
    expect(store.error).toBe('The embedding service is unavailable.')
  })

  it('selects exactly the ranked top k', async () => {
    const store = await opened()
    const ranking = store.setFilters({ text: 'novak', similarity: 'hejtman', k: 20 })
    await flush()
    last().answer(topK(['n1', 'n2']))
    await ranking

    const selecting = store.selectAllMatches()
    await flush()
    const request = idCalls()[idCalls().length - 1]
    expect(request.body).toMatchObject({ q: 'novak', ranking_query: 'hejtman', ranking: { mode: 'hybrid', k: 20, similar_to: null, include_source: false } })
    request.answer({ ids: ['n1', 'n2'], versions: {}, attributeVersions: {} })
    expect(await selecting).toBeNull()
    expect([...useAnnotationSelectionStore().ids]).toEqual(['n1', 'n2'])
  })
})

describe('ranked result labels', () => {
  it('names the top k, a shorter result and the annotations without a vector', () => {
    const result = { kind: 'top_k', mode: RetrievalMode.semantic, k: 100, truncated: true, coverage: { matching: 900, withVector: 863 } }
    expect(rankedLabel(result, 100)).toBe('Top 100 by meaning · 37 matching annotations have no vector yet and cannot be ranked')
    expect(rankedLabel({ ...result, mode: RetrievalMode.similar, truncated: false, coverage: { matching: 12, withVector: 12 } }, 12))
      .toBe('Top 100 most similar (12 found)')
    expect(rankedLabel({ ...result, k: 12, truncated: false, coverage: { matching: 13, withVector: 12 } }, 12))
      .toBe('Top 12 by meaning (all that could be ranked) · 1 matching annotation has no vector yet and cannot be ranked')
    expect(rankedLabel({ kind: 'complete' }, 10)).toBeNull()
  })

  it('says how the similarity text ranks without filtering', () => {
    expect(similarityHintText()).toMatch(/annotation and its left and right context \(BM25\).*whatever Contains words searches in.*excludes nothing/)
  })

  it('shows the source of Find similar as a reference chip, and the words and similarity as separate chips', () => {
    const source = row('a', 'Jan Novák z Lhoty, hejtman a pozdější starosta obce')
    const chips = concordanceChips(withMode(filters({ similarTo: source })), [], [], [])
    expect(chips).toEqual([{
      key: 'similar',
      group: 'Similar to',
      label: '\'Jan Novák z Lhoty, hejtman a pozdější s…\'',
      opens: source,
      remove: { similarTo: null, includeSource: false }
    }])
    expect(concordanceChips(withMode(filters({ text: 'novak', similarity: 'hejtman' })), [], [], []).map(c => [c.group, c.label, c.remove]))
      .toEqual([['Contains words in annotation', 'novak', { text: '' }], ['Similar meaning', 'hejtman', { similarity: '' }]])
  })
})

describe('ranked components', () => {
  const mounted: VueWrapper[] = []
  afterEach(() => {
    mounted.splice(0).forEach(w => w.unmount())
    document.body.innerHTML = ''
  })
  const mountIt = <T>(component: T, props: Record<string, unknown>) => {
    const wrapper = mount(component as never, { props: props as never, global: { plugins: [Quasar] }, attachTo: document.body })
    mounted.push(wrapper)
    return wrapper
  }
  const select = (w: VueWrapper, label: string) => w.findAllComponents(QSelect).find(s => s.props('label') === label)

  it('offers independent Words and Similarity inputs, no Find by or top-k selector', async () => {
    const toolbar = mountIt(ConcordanceToolbar, { filters: defaultFilters(), tags: [], documents: [] })
    const input = (label: string) => toolbar.findAllComponents(QInput).find(i => String(i.props('label')).startsWith(label))!
    expect(select(toolbar, 'Find by')).toBeUndefined()
    expect(select(toolbar, 'Top')).toBeUndefined()
    expect(select(toolbar, 'Sort by')).toBeUndefined() // the rows are sorted by the table's headers
    expect(select(toolbar, 'Search in')).toBeDefined() // the scope belongs to the words

    input('Contains words').vm.$emit('update:modelValue', 'novak')
    input('Similar meaning').vm.$emit('update:modelValue', 'hejtman')
    expect(toolbar.emitted('change')).toEqual([[{ text: 'novak' }], [{ similarity: 'hejtman' }]])
    expect(toolbar.findAllComponents(QCheckbox).find(c => c.props('label') === 'Include source')).toBeUndefined()

    await toolbar.setProps({ filters: withMode(filters({ similarTo: row('a') })) } as never)
    const include = toolbar.findAllComponents(QCheckbox).find(c => c.props('label') === 'Include source')!
    include.vm.$emit('update:modelValue', true)
    expect(toolbar.emitted('change')![2]).toEqual([{ includeSource: true }])
  })

  it('opens the source from its reference chip', async () => {
    const source = row('a', 'Praha')
    const chips = mountIt(ConcordanceFilterChips, {
      filters: withMode(filters({ similarTo: source })), tags: [], documents: [], attributes: []
    })
    const chip = chips.findComponent(QChip)
    expect(chip.props('clickable')).toBe(true)
    expect(chip.props('removeAriaLabel')).toBe('Stop finding annotations similar to \'Praha\'')
    await chip.trigger('click')
    expect(chips.emitted('open')).toEqual([[source]])
  })

  it('shows ranks and offers Find similar in the row menu', async () => {
    const table = mountIt(ConcordanceTable, { rows: [row('a'), row('b')], tags: [], selected: new Set(), rankStart: 51, similar: true })
    expect(table.findAll('[data-testid="kwic-rank"]').map(r => r.text())).toEqual(['#51', '#52'])
    await table.findAll('[data-testid="kwic-row"]')[1].trigger('contextmenu')
    await flush()
    const item = document.querySelector<HTMLElement>('[data-testid="kwic-row-similar"]')!
    item.click()
    expect(table.emitted('similar')).toEqual([[row('b')]])

    await table.setProps({ rankStart: null } as never)
    expect(table.findAll('[data-testid="kwic-rank"]')).toHaveLength(0)
  })

  it('says that select all takes the ranked top k only', () => {
    const bar = mountIt(SelectionBar, {
      selectedCount: 0,
      total: 100,
      ranked: true,
      hiddenSelected: 0,
      shownError: null,
      allSelected: false,
      resolving: false,
      tags: [],
      running: false,
      progress: 0,
      runningTarget: 0,
      report: null
    })
    expect(bar.findAllComponents(QBtn).find(b => b.attributes('data-testid') === 'select-all-matches')!.text())
      .toBe('Select these top 100')
  })

  it('says how many rows have no sort key yet and where they are listed (#666)', () => {
    expect(unsortableLabel(null, false)).toBeNull()
    expect(unsortableLabel(0, false)).toBeNull()
    expect(unsortableLabel(1, false)).toBe('1 annotation is not sortable yet and listed first')
    expect(unsortableLabel(37, true)).toBe('37 annotations are not sortable yet and listed last')
  })
})
