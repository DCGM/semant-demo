import { describe, expect, it } from 'vitest'
import { SpanType, type TagSpan } from 'src/generated/api'
import { filterAndSortSuggestions, getCreatedTime, toggleVisibleSuggestions, type ProposalFilters } from
  'src/features/annotations/aiSuggestionPresentation'

const defaults: ProposalFilters = { tagId: null, minimumConfidence: null, reason: '' }
const order = new Map([['z', 30], ['b', 4], ['a', 10]])
const span = (id: string, chunkId: string, start: number, opts: Partial<TagSpan> = {}): TagSpan => ({
  id, chunkId, start, end: start + 2, tagId: 't1', type: SpanType.auto, ...opts
})
const entry = (s: TagSpan) => ({ span: s })
const ids = (xs: { span: TagSpan }[]) => xs.map((e) => e.span.id)

describe('AI suggestion panel presentation', () => {
  it('sorts by numeric document order and offsets, never UUID order', () => {
    const list = [
      entry(span('c', 'z', 0)), entry(span('d', 'a', 3)),
      entry(span('b', 'b', 2)), entry(span('a', 'b', 2)),
      entry(span('e', 'b', 2, { end: 3 }))
    ]
    expect(ids(filterAndSortSuggestions(list, defaults, 'document', false, order)))
      .toEqual(['e', 'a', 'b', 'd', 'c'])
  })

  it('keeps missing confidence and explanations last in both directions with ID ties', () => {
    const list = [entry(span('b', 'b', 1, { confidence: 0.7, reason: 'zebra' })),
      entry(span('c', 'a', 1, { confidence: null, reason: null })),
      entry(span('a', 'z', 1, { confidence: 0.7, reason: 'Apple' }))]
    expect(ids(filterAndSortSuggestions(list, defaults, 'confidence', true, order)))
      .toEqual(['a', 'b', 'c'])
    expect(ids(filterAndSortSuggestions(list, defaults, 'confidence', false, order)))
      .toEqual(['a', 'b', 'c'])
    expect(ids(filterAndSortSuggestions(list, defaults, 'explanation', false, order)))
      .toEqual(['a', 'b', 'c'])
    expect(ids(filterAndSortSuggestions(list, defaults, 'explanation', true, order)))
      .toEqual(['b', 'a', 'c'])
  })

  it('combines tag, raw confidence threshold, and trimmed substring filters', () => {
    const list = [entry(span('a', 'a', 0, { confidence: 0.704, reason: '  Some Explanation' })),
      entry(span('b', 'a', 1, { confidence: 0.7, reason: 'Some other' })),
      entry(span('c', 'a', 2, { confidence: null, reason: 'Some explanation' })),
      entry(span('d', 'a', 3, { confidence: 0.8, reason: 'Some explanation', tagId: 't2' }))]
    const filters = { tagId: 't1', minimumConfidence: 0.701, reason: '  EXPLANATION  ' }
    expect(ids(filterAndSortSuggestions(list, filters, 'confidence', true, order))).toEqual(['a'])
    expect(filterAndSortSuggestions(list, { ...filters, reason: 'missing' }, 'confidence', true, order))
      .toHaveLength(0)
    expect(filterAndSortSuggestions(list, defaults, 'confidence', true, order)).toHaveLength(4)
  })

  it('keeps real creation dates ordered, with missing data last and no fabricated date', () => {
    const old = span('old', 'a', 1, { createdAt: new Date('2022-01-01T00:00:00Z') })
    const fresh = span('new', 'a', 1, { createdAt: new Date('2024-01-01T00:00:00Z') })
    const unknown = span('unknown', 'a', 1)
    expect(getCreatedTime(unknown)).toBeNull()
    const list = [entry(unknown), entry(old), entry(fresh)]
    expect(ids(filterAndSortSuggestions(list, defaults, 'created', true, order)))
      .toEqual(['new', 'old', 'unknown'])
    expect(ids(filterAndSortSuggestions(list, defaults, 'created', false, order)))
      .toEqual(['old', 'new', 'unknown'])
  })

  it('select-all changes only matching IDs and retains previously hidden IDs', () => {
    const selected = new Set(['hidden'])
    const shown = [entry(span('a', 'a', 1)), entry(span('b', 'b', 2))]
    const checked = toggleVisibleSuggestions(selected, shown, true)
    expect([...checked].sort()).toEqual(['a', 'b', 'hidden'])
    expect([...toggleVisibleSuggestions(checked, shown, false)]).toEqual(['hidden'])
    expect([...selected]).toEqual(['hidden'])
  })

  it('keeps historical dates null, accepts ISO dates and reverses chronology', () => {
    const old = span('a', 'a', 1, { createdAt: new Date('2020-01-01T00:00:00Z') })
    const newest = span('b', 'a', 1, { createdAt: new Date('2026-01-01T00:00:00Z') })
    const unknown = span('c', 'a', 1, { createdAt: null })
    const list = [entry(unknown), entry(newest), entry(old)]
    expect(ids(filterAndSortSuggestions(list, defaults, 'created', false, order)))
      .toEqual(['a', 'b', 'c'])
    expect(ids(filterAndSortSuggestions(list, defaults, 'created', true, order)))
      .toEqual(['b', 'a', 'c'])
  })

  it('keeps absent confidence when no threshold and excludes it at an active zero threshold', () => {
    const list = [entry(span('a', 'a', 0, { confidence: null })),
      entry(span('b', 'a', 1, { confidence: 0 }))]
    expect(filterAndSortSuggestions(list, defaults, 'confidence', true, order)).toHaveLength(2)
    expect(ids(filterAndSortSuggestions(list,
      { ...defaults, minimumConfidence: 0 }, 'confidence', true, order))).toEqual(['b'])
  })

  it('does not mutate the canonical input, including with over 2000 proposals', () => {
    const list = Array.from({ length: 2100 }, (_, i) => entry(span(String(i), 'a', i,
      { confidence: i / 2100 })))
    const sorted = filterAndSortSuggestions(list, defaults, 'confidence', true, order)
    expect(sorted).toHaveLength(2100)
    expect(sorted[0]?.span.id).toBe('2099')
    expect(list[0]?.span.id).toBe('0')
    expect(filterAndSortSuggestions(list.slice(0, 1255), defaults, 'document', false, order))
      .toHaveLength(1255)
  })
})
