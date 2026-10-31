import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { QBtn, QCheckbox, QOptionGroup, QRadio, QSelect, Quasar } from 'quasar'

import { Cardinality, ValueKind, type AnnotationListRow, type Attribute } from 'src/generated/api'
import {
  assignReportSummary, cannotAssign, clearChange, pickChange
} from 'src/features/attributes/assignment'
import {
  ASSIGN_BATCH, refusedWhole, useAttributeAssignStore, type AssignReport
} from 'src/features/attributes/attributeAssignStore'
import AttributeValuePicker from 'src/features/attributes/AttributeValuePicker.vue'
import AssignAttributeDialog from 'src/features/attributes/AssignAttributeDialog.vue'
import ConcordanceTable from 'src/features/annotations/concordance/ConcordanceTable.vue'
import AnnotationAttributes from 'src/features/annotations/concordance/AnnotationAttributes.vue'
import SelectionBar from 'src/features/annotations/concordance/SelectionBar.vue'
import { useConcordanceStore } from 'src/features/annotations/concordance/concordanceStore'
import { useAnnotationSelectionStore } from 'src/features/annotations/annotationSelectionStore'
import { endSession } from 'src/shared/api'

// Assigning attribute values in the annotation workspace (#331, ADR 0011): which assignment a
// pick means, one assignment per annotation at a time with its attribute version, the server's
// answer (versions and values) replacing the rows' copy, per-item reports, the attribute filters
// and the column, sidebar, picker and batch dialog.

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))
/** An assignment's answers, not looked at. */
const ignore = vi.fn()

const speaker = (extra: Partial<Attribute> = {}): Attribute => ({
  id: 'a1',
  name: 'Speaker',
  cardinality: Cardinality.single,
  allTags: false,
  tagIds: ['tag-1'],
  values: [
    { id: 'v1', label: 'politician', kind: ValueKind.value },
    { id: 'v2', label: 'journalist', kind: ValueKind.value },
    { id: 'v3', label: 'old', kind: ValueKind.value, retired: true },
    { id: 'vu', label: 'Unknown', kind: ValueKind.unknown }
  ],
  ...extra
})
const topic = (extra: Partial<Attribute> = {}) => speaker({ id: 'a2', name: 'Topic', cardinality: Cardinality.multi, ...extra })
const value = (attribute: Attribute, id: string) => attribute.values!.find(v => v.id === id)!

const row = (id: string, extra: Partial<AnnotationListRow> = {}): AnnotationListRow => ({
  id,
  tagId: 'tag-1',
  type: 'pos',
  chunkId: 'chunk-1',
  documentId: 'doc-1',
  start: 0,
  end: 4,
  revision: 1,
  textStatus: 'ready',
  text: id,
  documentAvailable: true,
  documentTitle: 'Kronika',
  documentYear: 1851,
  editVersion: 3,
  attributeVersion: 0,
  attributes: {},
  ...extra
} as AnnotationListRow)

/** Fetch stand-in: each call waits until the test answers it. */
function controlledFetch () {
  const calls: { url: URL, body: Record<string, unknown>, answer: (body: unknown, status?: number) => void }[] = []
  const fetchMock = vi.fn((input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => new Promise<Response>((resolve) => {
    calls.push({
      url: new URL(String(input)),
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : {},
      answer: (body, status = 200) => resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
    })
  }))
  return { calls, fetchMock }
}

describe('what a pick means', () => {
  it('replaces the value of a single-valued attribute', () => {
    expect(pickChange(speaker(), ['v1'], value(speaker(), 'v2'), true)).toEqual({ mode: 'replace', valueIds: ['v2'] })
  })

  it('adds and removes values of a multi-valued attribute', () => {
    expect(pickChange(topic(), ['v1'], value(topic(), 'v2'), true)).toEqual({ mode: 'add', valueIds: ['v2'] })
    expect(pickChange(topic(), ['v1', 'v2'], value(topic(), 'v1'), false)).toEqual({ mode: 'remove', valueIds: ['v1'] })
  })

  it('lets Unknown and Not applicable stand alone', () => {
    expect(pickChange(topic(), ['v1', 'v2'], value(topic(), 'vu'), true)).toEqual({ mode: 'replace', valueIds: ['vu'] })
    expect(pickChange(topic(), ['vu'], value(topic(), 'v1'), true)).toEqual({ mode: 'replace', valueIds: ['v1'] })
  })

  it('clears everything held, retired values included', () => {
    expect(clearChange(['v1', 'v3'])).toEqual({ mode: 'remove', valueIds: ['v1', 'v3'] })
  })

  it('says why an annotation cannot take values', () => {
    expect(cannotAssign(speaker(), row('a'))).toBeNull()
    expect(cannotAssign(speaker(), row('a', { type: 'auto' }))).toMatch(/Only confirmed/)
    expect(cannotAssign(speaker(), row('a', { tagId: 'tag-2' }))).toMatch(/does not apply/)
    expect(cannotAssign(speaker({ allTags: true, tagIds: [] }), row('a', { tagId: 'tag-2' }))).toBeNull()
    expect(cannotAssign(speaker({ retired: true }), row('a'))).toMatch(/retired/)
  })
})

describe('attribute assign store', () => {
  const originalFetch = globalThis.fetch
  let calls: ReturnType<typeof controlledFetch>['calls']
  const assignCalls = () => calls.filter(c => c.url.pathname.endsWith('/annotations/attributes/assign'))
  const ids = (n: number) => Array.from({ length: n }, (_, i) => `id-${i}`)

  beforeEach(() => {
    setActivePinia(createPinia())
    const controlled = controlledFetch()
    calls = controlled.calls
    globalThis.fetch = controlled.fetchMock as typeof fetch
    useAnnotationSelectionStore().enter('col-1')
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('sends parts with each annotation\'s attribute version and files every outcome apart', async () => {
    const assign = useAttributeAssignStore()
    const selection = useAnnotationSelectionStore()
    const targets = ids(ASSIGN_BATCH + 5).map((id, i) => [id, i % 3] as const)
    selection.add(targets.map(([id]) => [id, 7] as const), Object.fromEntries(targets))
    const answers: unknown[] = []
    const running = assign.assign('col-1', 'a1', { mode: 'add', valueIds: ['v1'] }, targets, r => answers.push(r))
    await flush()

    expect(assignCalls()[0].url.pathname).toBe('/api/user_collections/col-1/annotations/attributes/assign')
    expect(assignCalls()[0].body).toMatchObject({
      attribute_id: 'a1', mode: 'add', value_ids: ['v1'], source: 'manual', annotation_ids: ids(ASSIGN_BATCH)
    })
    expect((assignCalls()[0].body.expected_versions as Record<string, number>)['id-4']).toBe(1)
    expect(assign.pending.has('id-0')).toBe(true)

    assignCalls()[0].answer({
      outcome: 'partial',
      succeeded: [...ids(ASSIGN_BATCH).slice(7), 'id-4', 'id-5'],
      failed: [
        { item_id: 'id-0', step: 'edit_conflict', message: 'changed' },
        { item_id: 'id-1', step: 'check_annotation_type', message: 'not approved' },
        { item_id: 'id-2', step: 'find_annotation', message: 'gone' },
        { item_id: 'id-3', step: 'update_attributes', message: 'timeout', uncertain: true },
        { item_id: 'id-4', step: 'record_attribute_changes', message: 'sql down' },
        // A failed read is no missing annotation: it is retried, never dropped from the selection.
        { item_id: 'id-6', step: 'read_annotation', message: 'WeaviateTimeoutError: storage write failed', uncertain: true }
      ],
      versions: { 'id-0': 9, 'id-5': 3 },
      values: { 'id-0': ['v2'], 'id-5': ['v1'] }
    })
    await flush()
    expect(assignCalls()[1].body).toMatchObject({ annotation_ids: ids(ASSIGN_BATCH + 5).slice(ASSIGN_BATCH) })
    // A gateway error: the part may have been applied.
    assignCalls()[1].answer({ detail: 'bad gateway' }, 502)
    const report = await running

    expect(answers).toHaveLength(1)
    expect(report?.conflicts).toEqual([['id-0', 9]])
    expect(report?.refused).toEqual([{ id: 'id-1', step: 'check_annotation_type', message: 'not approved' }])
    expect(report?.missing).toEqual(['id-2'])
    expect(report?.unrecorded).toEqual(['id-4'])
    expect(report?.failed.map(f => [f.id, f.uncertain])).toEqual([
      ['id-3', true], ['id-6', true], ...ids(ASSIGN_BATCH + 5).slice(ASSIGN_BATCH).map(id => [id, true])])
    // Only this user's saved versions move the selection on; a conflict keeps the selected one.
    expect([selection.attributeVersionOf('id-5'), selection.attributeVersionOf('id-0')]).toEqual([3, 0])
    expect(assign.pending.size).toBe(0)
    // A headline, then each count next to its own reason.
    const summary = assignReportSummary({
      ...report!,
      refused: [...report!.refused,
        { id: 'x', step: 'check_value', message: 'Unknown and Not applicable cannot be combined with other values.' }]
    }, speaker())
    expect(summary.title).toBe(`"Speaker": saved ${ASSIGN_BATCH - 5} of ${ASSIGN_BATCH + 5} annotations`)
    expect(summary.lines.filter(l => l.label === 'not changed')).toEqual([
      { count: 1, label: 'not changed', detail: 'Only confirmed annotations take values.' },
      // Reasons with several causes are the server's own words.
      { count: 1, label: 'not changed', detail: 'Unknown and Not applicable cannot be combined with other values.' }
    ])
    expect(summary.lines.map(l => [l.count, l.label])).toEqual([
      [7, 'uncertain'], [1, 'not saved'], [1, 'not changed'], [1, 'not changed'], [1, 'no longer exist'],
      [1, 'saved without history'], [null, 'Saved changes are kept.']
    ])

    // A retry sends only the failed and uncertain items, at the versions they were sent with.
    const retrying = assign.retry('col-1', ignore)
    await flush()
    const resent = ['id-3', 'id-6', ...ids(ASSIGN_BATCH + 5).slice(ASSIGN_BATCH)]
    expect(assignCalls()[2].body).toMatchObject({ annotation_ids: resent })
    assignCalls()[2].answer({ outcome: 'complete', succeeded: resent, failed: [] })
    const retried = await retrying
    expect([retried?.failed.length, retried?.conflicts.length]).toEqual([0, 1])
  })

  it('takes a 503 as a refusal, not as a lost answer, and shows no result for a request refused as a whole', async () => {
    const assign = useAttributeAssignStore()
    const refused = assign.assign('col-1', 'a1', { mode: 'add', valueIds: ['v1'] }, [['a', 0]], ignore)
    await flush()
    assignCalls()[0].answer({ detail: 'Attribute assignments are not enabled on this store.' }, 503)
    const report = await refused
    expect(report?.error).toBe('Attribute assignments are not enabled on this store.')
    expect(report?.failed.map(f => f.uncertain)).toEqual([false])
    expect(refusedWhole(report!)).toBe(true)
    // The dialog says why; the selection bar shows no "saved 0 of 1" for it.
    expect(assign.report).toBeNull()

    // Refused after a first part was saved: reported, the rest not sent.
    const partly = assign.assign('col-1', 'a1', { mode: 'add', valueIds: ['v1'] },
      ids(ASSIGN_BATCH + 1).map(id => [id, 0] as const), ignore)
    await flush()
    assignCalls()[1].answer({ outcome: 'complete', succeeded: ids(ASSIGN_BATCH), failed: [] })
    await flush()
    assignCalls()[2].answer({ detail: 'not enabled' }, 503)
    const second = await partly
    expect([second?.saved.length, second?.failed.map(f => f.uncertain), refusedWhole(second!)]).toEqual([ASSIGN_BATCH, [false], false])
    expect(assign.report).toBe(second)
  })

  it('sends at most one assignment per annotation at a time', async () => {
    const assign = useAttributeAssignStore()
    const first = assign.assignOne('col-1', 'a1', { mode: 'replace', valueIds: ['v1'] }, ['r1', 0], ignore)
    await flush()
    expect(await assign.assignOne('col-1', 'a1', { mode: 'replace', valueIds: ['v2'] }, ['r1', 0], ignore)).toBeNull()
    expect(await assign.assign('col-1', 'a1', { mode: 'add', valueIds: ['v2'] }, [['r1', 0], ['r2', 0]], ignore)).toBeNull()
    expect(assignCalls()).toHaveLength(1)

    assignCalls()[0].answer({ outcome: 'complete', succeeded: ['r1'], failed: [], versions: { r1: 1 }, values: { r1: ['v1'] } })
    expect((await first)?.saved).toEqual(['r1'])
    expect(assign.isPending('r1')).toBe(false)
    // The single assignment does not replace the selection's report.
    expect(assign.report).toBeNull()
  })

  it('stops a selection\'s assignment once its members change, and drops answers after the session ended', async () => {
    const assign = useAttributeAssignStore()
    const selection = useAnnotationSelectionStore()
    selection.add(ids(ASSIGN_BATCH + 1).map(id => [id, 0] as const))
    const running = assign.assign('col-1', 'a1', { mode: 'add', valueIds: ['v1'] }, ids(ASSIGN_BATCH + 1).map(id => [id, 0] as const), ignore)
    await flush()
    selection.remove(['id-0'])
    assignCalls()[0].answer({ outcome: 'complete', succeeded: ids(ASSIGN_BATCH), failed: [] })
    const report = await running
    expect([report?.notSent, assignCalls().length]).toEqual([1, 1])

    const late = assign.assignOne('col-1', 'a1', { mode: 'add', valueIds: ['v1'] }, ['x', 0], () => { throw new Error('applied') })
    await flush()
    endSession()
    assignCalls()[1].answer({ outcome: 'complete', succeeded: ['x'], failed: [], versions: { x: 1 } })
    expect(await late).toBeNull()
  })
})

describe('concordance store and attributes', () => {
  const originalFetch = globalThis.fetch
  let calls: ReturnType<typeof controlledFetch>['calls']

  beforeEach(() => {
    setActivePinia(createPinia())
    const controlled = controlledFetch()
    calls = controlled.calls
    globalThis.fetch = controlled.fetchMock as typeof fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  async function opened () {
    const store = useConcordanceStore()
    const opening = store.open('col-1')
    await flush()
    calls.find(c => c.url.pathname.endsWith('/annotations'))!.answer({
      rows: [row('r1', { attributes: { a1: ['v1'] }, attributeVersion: 2 }), row('r2')], total: 2, offset: 0, limit: 50
    })
    calls.find(c => c.url.pathname.endsWith('/annotations/documents'))!.answer([])
    await opening
    return store
  }

  it('sends the attribute filters with the rows and with id resolution', async () => {
    const store = await opened()
    const filtering = store.setFilters({ attributeValues: ['a1:v1', 'a1:v2'], attributeUnassigned: ['a2'] })
    await flush()
    const rows = calls.filter(c => c.url.pathname.endsWith('/annotations')).at(-1)!
    expect(rows.url.searchParams.getAll('attribute')).toEqual(['a1:v1', 'a1:v2'])
    expect(rows.url.searchParams.getAll('unassigned')).toEqual(['a2'])
    rows.answer({ rows: [], total: 0, offset: 0, limit: 50 })
    await filtering

    const selecting = store.selectAllMatches()
    await flush()
    const resolve = calls.filter(c => c.url.pathname.endsWith('/annotations/ids')).at(-1)!
    expect(resolve.body).toMatchObject({ attribute_values: ['a1:v1', 'a1:v2'], attribute_unassigned: ['a2'] })
    resolve.answer({ ids: ['r1'], versions: { r1: 3 }, attribute_versions: { r1: 5 } })
    await selecting
    expect(useAnnotationSelectionStore().attributeVersionOf('r1')).toBe(5)
  })

  it('keeps the attribute version of rows checked on the page', async () => {
    const store = await opened()
    store.setPageSelected(true)
    expect(useAnnotationSelectionStore().attributeVersionOf('r1')).toBe(2)
  })

  it('shows the values and versions an assignment answered instead of its own copy', async () => {
    const store = await opened()
    const selection = useAnnotationSelectionStore()
    selection.focus(store.rows[0]!)
    store.applyAssignment('a1', { outcome: 'complete', succeeded: ['r1'], failed: [], versions: { r1: 3, r2: 4 }, values: { r1: [], r2: ['v2'] } })
    expect(store.rows.map(r => [r.attributes, r.attributeVersion])).toEqual([[{}, 3], [{ a1: ['v2'] }, 4]])
    expect(selection.focused?.attributeVersion).toBe(3)
    expect(selection.focusedGone).toBe(false)
  })
})

describe('attribute components', () => {
  const mounted: VueWrapper[] = []
  afterEach(() => {
    mounted.splice(0).forEach(w => w.unmount())
    document.body.innerHTML = ''
  })
  const mountIt = <T>(component: T, props: Record<string, unknown>) => {
    const wrapper = mount(component as never, {
      props: props as never, global: { plugins: [Quasar], stubs: { RouterLink: true } }, attachTo: document.body
    })
    mounted.push(wrapper)
    return wrapper
  }

  it('shows the attribute column only when chosen, editable on rows that can take values', () => {
    const rows = [row('r1', { attributes: { a1: ['v1', 'gone'] } }), row('r2', { type: 'auto' })]
    const without = mountIt(ConcordanceTable, { rows, tags: [], selected: new Set() })
    expect(without.findAll('[data-testid="kwic-attribute"]')).toHaveLength(0)

    const table = mountIt(ConcordanceTable, { rows, tags: [], selected: new Set(), attribute: speaker() })
    const cells = table.findAll('[data-testid="kwic-attribute"]')
    expect(cells[0]!.text()).toContain('politician')
    expect(cells[0]!.text()).toContain('Unknown value')
    expect(cells[0]!.find('[data-testid="kwic-attribute-edit"]').exists()).toBe(true)
    expect(cells[1]!.find('[data-testid="kwic-attribute-edit"]').exists()).toBe(false)
    expect(cells[1]!.text()).toContain('Only confirmed annotations take attribute values.')
  })

  it('picks with radio buttons for one value and checkboxes for several, and waits while saving', async () => {
    const single = mountIt(AttributeValuePicker, { attribute: speaker(), current: ['v1'] })
    // A retired value is offered only while held.
    expect(single.findAllComponents(QRadio).map(r => r.props('val'))).toEqual(['v1', 'v2', 'vu'])
    single.findAllComponents(QRadio)[1]!.vm.$emit('update:modelValue', 'v2')
    expect(single.emitted('change')).toEqual([[{ mode: 'replace', valueIds: ['v2'] }]])

    const multi = mountIt(AttributeValuePicker, { attribute: topic(), current: ['v1', 'v3'] })
    expect(multi.findAllComponents(QCheckbox)).toHaveLength(4)
    multi.findAllComponents(QCheckbox)[0]!.vm.$emit('update:modelValue', false)
    expect(multi.emitted('change')).toEqual([[{ mode: 'remove', valueIds: ['v1'] }]])
    await multi.find('[data-testid="attribute-pick-clear"]').trigger('click')
    expect(multi.emitted('change')![1]).toEqual([{ mode: 'remove', valueIds: ['v1', 'v3'] }])

    const busy = mountIt(AttributeValuePicker, { attribute: topic(), current: [], busy: true })
    busy.findAllComponents(QCheckbox)[0]!.vm.$emit('update:modelValue', true)
    expect(busy.emitted('change')).toBeUndefined()
  })

  it('lists the attributes of the open annotation\'s tag and says why a proposal takes none', () => {
    const attributes = [speaker(), topic({ tagIds: ['tag-2'] })]
    const confirmed = mountIt(AnnotationAttributes, { row: row('r1', { attributes: { a1: ['v2'], a2: ['v1'] } }), attributes })
    expect(confirmed.find('[data-testid="annotation-attribute-a1"]').text()).toContain('journalist')
    // Values of an attribute that no longer applies stay visible and removable (#500).
    expect(confirmed.find('[data-testid="annotation-attribute-a2"]').text()).toContain('does not apply to this tag')

    const proposal = mountIt(AnnotationAttributes, { row: row('r2', { type: 'auto' }), attributes })
    expect(proposal.find('[data-testid="annotation-attributes-note"]').text()).toMatch(/Only confirmed/)
    expect(proposal.find('[data-testid="annotation-attribute-edit"]').exists()).toBe(false)

    const none = mountIt(AnnotationAttributes, { row: row('r3', { tagId: 'tag-9' }), attributes })
    expect(none.find('[data-testid="annotation-attributes-empty"]').text()).toContain('No attributes apply to this tag.')
  })

  it('shows a selection\'s assignment result with retry and the changed ones apart', async () => {
    const report: AssignReport = {
      attributeId: 'a1',
      change: { mode: 'add', valueIds: ['v1'] },
      target: 4,
      saved: ['a'],
      conflicts: [['b', 2]],
      failed: [{ id: 'c', message: 'x', uncertain: true, version: 0 }],
      refused: [],
      missing: [],
      unrecorded: [],
      notSent: 0,
      error: null
    }
    const bar = mountIt(SelectionBar, {
      selectedCount: 4,
      total: 4,
      hiddenSelected: 0,
      shownError: null,
      allSelected: true,
      resolving: false,
      tags: [],
      running: false,
      progress: 0,
      runningTarget: 0,
      report: null,
      assignReport: report,
      assignAttribute: speaker()
    })
    expect(bar.find('[data-testid="assign-report-title"]').text()).toBe('"Speaker": saved 1 of 4 annotations')
    expect(bar.findAll('[data-testid="assign-report-lines"] li').map(li => li.text())).toEqual([
      '1uncertainThe server did not confirm; they may have been saved.',
      '1not savedChanged by someone else since you selected them.',
      'Saved changes are kept.'
    ])
    await bar.find('[data-testid="assign-retry"]').trigger('click')
    await bar.find('[data-testid="assign-show-changed"]').trigger('click')
    await bar.find('[data-testid="assign-attribute"]').trigger('click')
    expect([bar.emitted('assign-retry'), bar.emitted('assign-show-changed'), bar.emitted('assign')].map(e => e?.length))
      .toEqual([1, 1, 1])
  })
})

describe('assign attribute dialog', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  async function openDialog (save: ReturnType<typeof vi.fn>, attributes = [topic()]) {
    const wrapper = mount(AssignAttributeDialog as never, {
      props: { attributes, tags: [{ id: 'tag-1', name: 'Statement' }], count: 18, offPage: 3, save } as never,
      global: { plugins: [Quasar] },
      attachTo: document.body
    })
    ;(wrapper.vm as unknown as { show: () => void }).show()
    await flushPromises()
    return wrapper
  }
  const okButton = (w: VueWrapper) => w.findAllComponents(QBtn).find(b => /\d+$/.test(String(b.props('label'))))!
  const text = (id: string) => document.querySelector(`[data-testid="${id}"]`)?.textContent ?? ''

  it('names the target and what will happen, and keeps Unknown apart from other values', async () => {
    const save = vi.fn()
    const wrapper = await openDialog(save)
    expect(text('assign-target')).toMatch(/To 18 selected annotations,\s+3 of them not on this page\./)
    expect(okButton(wrapper).props('label')).toBe('Add to 18')
    const values = wrapper.findComponent(QOptionGroup)
    // The retired value is not offered for adding.
    expect((values.props('options') as { value: string }[]).map(o => o.value)).toEqual(['v1', 'v2', 'vu'])
    values.vm.$emit('update:modelValue', ['v1', 'v2'])
    await flushPromises()
    expect(text('assign-summary')).toContain('Add "politician" and "journalist" to "Topic" of 18 annotations.')
    expect(text('assign-summary')).toContain('(Statement)')
    values.vm.$emit('update:modelValue', ['v1', 'v2', 'vu'])
    await flushPromises()
    expect(wrapper.findComponent(QOptionGroup).props('modelValue')).toEqual(['vu'])
  })

  it('says that Remove and Clear also reach annotations that hide their values, and counts tags not loaded', async () => {
    const wrapper = await openDialog(vi.fn(), [topic({ tagIds: ['tag-1', 'tag-gone'] })])
    // A tag it cannot name is counted, never shown as "no tag".
    expect(text('assign-scope-note')).toContain('(2 selected tags) take values')
    wrapper.findAllComponents({ name: 'QBtnToggle' })[0]!.vm.$emit('update:modelValue', 'remove')
    await flushPromises()
    expect(text('assign-scope-note')).toContain('also from rejected annotations and annotations whose tag the attribute no longer applies to')
    expect(text('assign-scope-note')).not.toContain('take values')
  })

  it('stays open with the reason when the assignment was refused as a whole', async () => {
    const report: AssignReport = {
      attributeId: 'a2',
      change: { mode: 'add', valueIds: ['v1'] },
      target: 18,
      saved: [],
      conflicts: [],
      failed: [],
      refused: [],
      missing: [],
      unrecorded: [],
      notSent: 0,
      error: 'This attribute is retired; values can only be removed.'
    }
    const save = vi.fn().mockResolvedValue(report)
    const wrapper = await openDialog(save)
    wrapper.findComponent(QOptionGroup).vm.$emit('update:modelValue', ['v1'])
    await flushPromises()
    await okButton(wrapper).trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledWith('a2', { mode: 'add', valueIds: ['v1'] })
    expect(text('assign-error')).toContain('values can only be removed')
    expect(document.querySelector('[data-testid="assign-summary"]')).not.toBeNull()
  })

  it('sets or clears a single-valued attribute', async () => {
    const save = vi.fn().mockResolvedValue(null)
    const wrapper = await openDialog(save, [speaker(), topic()])
    wrapper.findComponent(QSelect).vm.$emit('update:modelValue', 'a1')
    await flushPromises()
    expect(okButton(wrapper).props('label')).toBe('Set on 18')
    const toggle = wrapper.findAllComponents({ name: 'QBtnToggle' })[0]!
    toggle.vm.$emit('update:modelValue', 'clear')
    await flushPromises()
    expect(text('assign-summary')).toContain('Remove every value of "Speaker" from 18 annotations.')
    await okButton(wrapper).trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledWith('a1', { mode: 'remove', valueIds: ['v1', 'v2', 'v3', 'vu'] })
  })
})
