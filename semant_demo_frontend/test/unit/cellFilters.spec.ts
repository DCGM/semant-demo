import { describe, expect, it } from 'vitest'
import {
  Cardinality, RetrievalMode, SpanType, TextScope, TextStatus, ValueKind, type AnnotationListRow, type Attribute
} from 'src/generated/api'
import { rowFilterGroups, wordFilterGroup, type CellFilterGroup } from 'src/features/annotations/concordance/cellFilters'
import { defaultFilters, type ConcordanceFilters } from 'src/features/annotations/concordance/concordanceStore'

// #665: filters offered from a row's displayed values and from words selected in its text.

const role: Attribute = {
  id: 'role',
  name: 'Role',
  cardinality: Cardinality.multi,
  allTags: true,
  values: [
    { id: 'judge', label: 'Judge', kind: ValueKind.value, order: 0 },
    { id: 'mayor', label: 'Mayor', kind: ValueKind.value, order: 1 }
  ]
} as unknown as Attribute

function row (overrides: Partial<AnnotationListRow> = {}): AnnotationListRow {
  return {
    id: 'a',
    tagId: 't',
    type: SpanType.pos,
    text: 'Jan Novák',
    textStatus: TextStatus.ready,
    documentId: 'd',
    documentTitle: 'Kronika obce Lhota',
    documentYear: 1851,
    documentAvailable: true,
    attributes: { role: ['judge'] },
    ...overrides
  } as AnnotationListRow
}

const filters = (f: Partial<ConcordanceFilters> = {}): ConcordanceFilters => ({ ...defaultFilters(), ...f })
const groups = (f: Partial<ConcordanceFilters> = {}, r = row(), attributes = [role]) =>
  rowFilterGroups(r, filters(f), { tagName: 'Osoba', attributes })
const action = (list: CellFilterGroup[], key: string) => list.flatMap(g => g.actions).find(a => a.key === key)
const keys = (list: CellFilterGroup[]) => list.flatMap(g => g.actions.map(a => a.key))

describe('row value filters', () => {
  it('offers Only this for each value, in the order of the cells, and Exclude for the status', () => {
    const list = groups()
    expect(list.map(g => g.label)).toEqual([
      'Role · Judge', 'Tag · Osoba', 'Status · Confirmed', 'Source · Kronika obce Lhota', 'Year · 1851'
    ])
    expect(keys(list)).toEqual([
      'attribute-only-role-judge', 'tag-only', 'status-only', 'status-exclude', 'source-only', 'year-only'
    ])
    expect(action(list, 'source-only')?.change).toEqual({ documentIds: ['d'] })
    expect(action(list, 'tag-only')?.change).toEqual({ tagIds: ['t'] })
    expect(action(list, 'status-only')?.change).toEqual({ types: [SpanType.pos] })
    expect(action(list, 'status-exclude')?.change).toEqual({ types: [SpanType.auto] })
    expect(action(list, 'year-only')?.change).toEqual({ documentFilters: { yearMin: 1851, yearMax: 1851 } })
    expect(action(list, 'attribute-only-role-judge')?.change).toEqual({ attributeValues: ['role:judge'], attributeUnassigned: [] })
  })

  it('composes with the other filters and keeps the rest of each field', () => {
    const list = groups({
      documentFilters: { yearMin: 1800, titleContains: ['kronika'] },
      attributeValues: ['role:mayor', 'other:x'],
      attributeUnassigned: ['role', 'gender']
    })
    // The year range replaces the range only; the title filter stays.
    expect(action(list, 'year-only')?.change).toEqual({ documentFilters: { titleContains: ['kronika'], yearMin: 1851, yearMax: 1851 } })
    expect(action(list, 'year-clear')?.change).toEqual({ documentFilters: { titleContains: ['kronika'] } })
    // A value replaces the attribute's own accepted values only.
    expect(action(list, 'attribute-only-role-judge')?.change).toEqual({ attributeValues: ['other:x', 'role:judge'], attributeUnassigned: ['gender'] })
    expect(action(list, 'attribute-clear-role')?.change).toEqual({ attributeValues: ['other:x'], attributeUnassigned: ['gender'] })
  })

  it('offers Clear for active fields and no Only for a value that already is the filter', () => {
    const list = groups({
      documentIds: ['d'],
      tagIds: ['t'],
      types: [SpanType.pos],
      documentFilters: { yearMin: 1851, yearMax: 1851 },
      attributeValues: ['role:judge']
    })
    expect(keys(list)).toEqual(['attribute-clear-role', 'tag-clear', 'status-clear', 'source-clear', 'year-clear'])
    expect(action(list, 'status-clear')?.change).toEqual({ types: defaultFilters().types })
    expect(action(list, 'source-clear')?.change).toEqual({ documentIds: [] })
    expect(action(list, 'tag-clear')?.change).toEqual({ tagIds: [] })
  })

  it('never excludes the last status', () => {
    const list = groups({ types: [SpanType.pos, SpanType.neg] }, row({ type: SpanType.neg }))
    expect(action(list, 'status-exclude')?.change).toEqual({ types: [SpanType.pos] })
    expect(action(groups({ types: [SpanType.neg] }, row({ type: SpanType.neg })), 'status-exclude')).toBeUndefined()
  })

  it('offers each of several values, and not assigned for a row without one', () => {
    const several = groups({}, row({ attributes: { role: ['judge', 'mayor'] } }))
    expect(several[0].label).toBe('Role · Judge, Mayor')
    expect(several[0].actions.map(a => a.label)).toEqual(['Only Judge', 'Only Mayor'])

    const none = groups({ attributeValues: ['role:judge'] }, row({ attributes: {} }))
    expect(none[0].label).toBe('Role · not assigned')
    expect(action(none, 'attribute-unassigned-role')?.change).toEqual({ attributeValues: [], attributeUnassigned: ['role'] })
    expect(keys(groups({ attributeUnassigned: ['role'] }, row({ attributes: {} })))).toContain('attribute-clear-role')
    expect(keys(groups({ attributeUnassigned: ['role'] }, row({ attributes: {} })))).not.toContain('attribute-unassigned-role')
  })

  it('offers no source or year filter for an unavailable source or a missing year', () => {
    expect(groups({}, row({ documentAvailable: false })).map(g => g.key)).not.toContain('source')
    expect(groups({}, row({ documentAvailable: false })).map(g => g.key)).not.toContain('year')
    expect(groups({}, row({ documentYear: null })).map(g => g.key)).not.toContain('year')
  })
})

describe('the filter by selected words', () => {
  it('filters by the selected words in the field they were selected in, with the matching rules', () => {
    const group = wordFilterGroup(' Novák, ', TextScope.annotation, filters())
    expect(group?.actions).toEqual([expect.objectContaining({
      label: 'Filter annotations containing “Novák”', change: { text: 'Novák', textScope: TextScope.annotation }
    })])
    expect(group?.caption).toBe('Each word must appear inside a word of the annotation, ignoring case but not diacritics. Not a phrase search.')
    expect(wordFilterGroup('do Lhoty', TextScope.context, filters())?.actions[0].label)
      .toBe('Filter annotations with “do Lhoty” in their context')
    expect(wordFilterGroup('hejtman Jan', TextScope.both, filters())?.actions[0].change)
      .toEqual({ text: 'hejtman Jan', textScope: TextScope.both })
  })

  it('adds the words to a text filter of the same field and replaces one of another field', () => {
    const same = wordFilterGroup('Novák jan', TextScope.annotation, filters({ text: 'Jan' }))
    expect(same?.actions[0].change).toEqual({ text: 'Jan Novák', textScope: TextScope.annotation })
    expect(same?.caption).not.toContain('Replaces')

    const other = wordFilterGroup('Lhoty', TextScope.context, filters({ text: 'Jan' }))
    expect(other?.actions[0].change).toEqual({ text: 'Lhoty', textScope: TextScope.context })
    expect(other?.caption).toContain('Replaces the text filter “Jan”.')
  })

  it('offers nothing without a new word', () => {
    expect(wordFilterGroup(' , – ', TextScope.annotation, filters())).toBeNull()
    expect(wordFilterGroup('jan', TextScope.annotation, filters({ text: 'Jan' }))).toBeNull()
    // A similarity text ranks and never changes the words filter; Find similar keeps it too.
    expect(wordFilterGroup('Jan', TextScope.annotation, filters({ mode: RetrievalMode.hybrid, similarity: 'x' }))).not.toBeNull()
    expect(wordFilterGroup('Jan', TextScope.annotation, filters({ mode: RetrievalMode.similar }))).not.toBeNull()
  })
})
