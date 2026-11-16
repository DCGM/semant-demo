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
  defaultFilters, modeChange, similarChange, useConcordanceStore, type ConcordanceFilters
} from 'src/features/annotations/concordance/concordanceStore'
import { concordanceChips, modeHintText, rankedLabel, unsortableLabel } from 'src/features/annotations/concordance/filterChips'
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

  it('waits for a text in a mode that ranks by it, then sends mode and k without a sort', async () => {
    const store = await opened()
    await store.setFilters(modeChange(RetrievalMode.semantic))
    expect(rowCalls()).toHaveLength(1)
    expect([store.needsText, store.page, store.error]).toEqual([true, null, null])

    const ranking = store.setFilters({ text: ' hejtman ', k: 200 })
    await flush()
    const params = last().url.searchParams
    expect(Object.fromEntries(['mode', 'k', 'q', 'sort', 'text_scope', 'similar_to'].map(k => [k, params.get(k)])))
      .toEqual({ mode: 'semantic', k: '200', q: 'hejtman', sort: null, text_scope: null, similar_to: null })
    last().answer(topK(['n1', 'n2']))
    await ranking
    expect(store.rows.map(r => r.id)).toEqual(['n1', 'n2'])
    expect(store.page?.result?.coverage).toEqual({ matching: 40, withVector: 3 })

    void store.setFilters({ ...modeChange(RetrievalMode.hybrid), textScope: TextScope.both })
    await flush()
    expect([last().url.searchParams.get('mode'), last().url.searchParams.get('text_scope')]).toEqual(['hybrid', 'both'])
  })

  it('finds similar annotations within the filters, dropping a text that ranked by meaning', async () => {
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
    expect([params.get('mode'), params.get('similar_to'), params.get('q'), params.getAll('tag_id'), params.get('include_source')])
      .toEqual(['similar', 'a', 'praha', ['t1'], null])

    void store.setFilters({ includeSource: true })
    await flush()
    expect(last().url.searchParams.get('include_source')).toBe('true')

    expect(similarChange(filters({ mode: RetrievalMode.semantic, text: 'hejtman' }), source))
      .toEqual({ mode: RetrievalMode.similar, similarTo: source, includeSource: false, text: '' })
    void store.setFilters(modeChange(RetrievalMode.lexical))
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

    const unavailable = store.setFilters({ ...modeChange(RetrievalMode.semantic), text: 'x' })
    await flush()
    last().answer({ detail: 'The embedding service is unavailable.' }, 503)
    await unavailable
    expect(store.error).toBe('The embedding service is unavailable.')
  })

  it('selects exactly the ranked top k', async () => {
    const store = await opened()
    const ranking = store.setFilters({ ...modeChange(RetrievalMode.semantic), text: 'hejtman', k: 20 })
    await flush()
    last().answer(topK(['n1', 'n2']))
    await ranking

    const selecting = store.selectAllMatches()
    await flush()
    const request = idCalls()[idCalls().length - 1]
    expect(request.body).toMatchObject({ q: 'hejtman', ranking: { mode: 'semantic', k: 20, similar_to: null, include_source: false } })
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

  it('says how each mode uses the text', () => {
    expect(modeHintText(RetrievalMode.semantic, TextScope.both)).toMatch(/closeness in meaning.*filters nothing/)
    expect(modeHintText(RetrievalMode.hybrid, TextScope.context)).toMatch(/left or right context \(BM25\)/)
    expect(modeHintText(RetrievalMode.similar, TextScope.annotation)).toMatch(/inside a word of the annotation/)
  })

  it('shows the source of Find similar as a reference chip that leaves the mode when removed', () => {
    const source = row('a', 'Jan Novák z Lhoty, hejtman a pozdější starosta obce')
    const chips = concordanceChips(filters({ mode: RetrievalMode.similar, similarTo: source }), [], [], [])
    expect(chips).toEqual([{
      key: 'similar',
      group: 'Similar to',
      label: '\'Jan Novák z Lhoty, hejtman a pozdější s…\'',
      opens: source,
      remove: { mode: RetrievalMode.lexical, similarTo: null, includeSource: false }
    }])
    expect(concordanceChips(filters({ mode: RetrievalMode.semantic, text: 'hejtman' }), [], [], [])[0].group).toBe('Meaning')
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

  it('chooses the mode and k, and disables sorting a ranked result', async () => {
    const toolbar = mountIt(ConcordanceToolbar, { filters: defaultFilters(), tags: [], documents: [] })
    expect((select(toolbar, 'Find by')!.props('options') as { label: string }[]).map(o => o.label))
      .toEqual(['Words', 'Meaning', 'Meaning and words'])
    expect(select(toolbar, 'Top')).toBeUndefined()
    select(toolbar, 'Find by')!.vm.$emit('update:modelValue', RetrievalMode.semantic)
    expect(toolbar.emitted('change')).toEqual([[{ mode: RetrievalMode.semantic, similarTo: null, includeSource: false }]])

    await toolbar.setProps({ filters: filters({ mode: RetrievalMode.semantic }) } as never)
    expect(select(toolbar, 'Search in')).toBeUndefined() // meaning is of the text alone
    expect(toolbar.findAllComponents(QInput).find(i => i.props('label') === 'Meaning of')).toBeDefined()
    expect(select(toolbar, 'Sort by')!.props('disable')).toBe(true)
    select(toolbar, 'Top')!.vm.$emit('update:modelValue', 500)
    expect(toolbar.emitted('change')![1]).toEqual([{ k: 500 }])

    await toolbar.setProps({ filters: filters({ mode: RetrievalMode.similar, similarTo: row('a') }) } as never)
    const similar = (select(toolbar, 'Find by')!.props('options') as { label: string, disable: boolean }[]).at(-1)
    expect(similar).toEqual({ value: RetrievalMode.similar, label: 'Similar', disable: true })
    const include = toolbar.findAllComponents(QCheckbox).find(c => c.props('label') === 'Include source')!
    include.vm.$emit('update:modelValue', true)
    expect(toolbar.emitted('change')![2]).toEqual([{ includeSource: true }])
  })

  it('opens the source from its reference chip', async () => {
    const source = row('a', 'Praha')
    const chips = mountIt(ConcordanceFilterChips, {
      filters: filters({ mode: RetrievalMode.similar, similarTo: source }), tags: [], documents: [], attributes: []
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
