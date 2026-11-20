import type { TagSpan } from 'src/generated/api'

/** Panel-only presentation; the shared pending list keeps its gutter ordering. */
export type ProposalSort = 'confidence' | 'document' | 'explanation' | 'created'

export interface ProposalFilters {
  tagId: string | null
  minimumConfidence: number | null // raw 0..1, inclusive; null means no filter
  reason: string
}

interface WithSpan { span: TagSpan }

// #460 records nullable provenance; never synthesize dates for historical spans.
export function getCreatedTime(span: TagSpan): number | null {
  const source = span.createdAt
  if (source == null) return null
  const timestamp = source instanceof Date ? source.getTime() : new Date(source).getTime()
  return Number.isFinite(timestamp) ? timestamp : null
}

/** Changing filters must never add or discard selected IDs outside the visible set. */
export function toggleVisibleSuggestions<T extends WithSpan>(
  selected: ReadonlySet<string>, visible: readonly T[], on: boolean
): Set<string> {
  const next = new Set(selected)
  for (const { span } of visible) {
    if (!span.id) continue
    if (on) next.add(span.id)
    else next.delete(span.id)
  }
  return next
}

function compareNullable<T> (a: T | null, b: T | null,
  compare: (a: T, b: T) => number, descending: boolean): number {
  // Missing values always last, even when sort direction is reversed.
  if (a === null) return b === null ? 0 : 1
  if (b === null) return -1
  const result = compare(a, b)
  return descending ? -result : result
}

function reasonOf(span: TagSpan): string | null {
  const trimmed = span.reason?.trim()
  return trimmed ? trimmed.toLocaleLowerCase() : null
}

/** Pure, deterministic selector, with AND filters and stable ID ties. */
export function filterAndSortSuggestions<T extends WithSpan>(
  entries: readonly T[], filters: ProposalFilters, sort: ProposalSort,
  descending: boolean, chunkOrder: ReadonlyMap<string, number>
): T[] {
  const query = filters.reason.trim().toLocaleLowerCase()
  const filtered = entries.filter(({ span }) => {
    if (filters.tagId !== null && span.tagId !== filters.tagId) return false
    if (filters.minimumConfidence !== null &&
      (span.confidence == null || span.confidence < filters.minimumConfidence)) return false
    if (query && !(span.reason ?? '').toLocaleLowerCase().includes(query)) return false
    return true
  })

  return filtered.sort((a, b) => {
    const left = a.span
    const right = b.span
    let result = 0
    if (sort === 'confidence') {
      result = compareNullable(left.confidence ?? null, right.confidence ?? null,
        (x, y) => x - y, descending)
    } else if (sort === 'explanation') {
      result = compareNullable(reasonOf(left), reasonOf(right),
        (x, y) => x.localeCompare(y), descending)
    } else if (sort === 'created') {
      result = compareNullable(getCreatedTime(left), getCreatedTime(right),
        (x, y) => x - y, descending)
    } else {
      // Caller disables this mode until all relevant canonical chunk orders exist.
      const leftOrder = chunkOrder.get(left.chunkId)
      const rightOrder = chunkOrder.get(right.chunkId)
      if (leftOrder !== undefined && rightOrder !== undefined) {
        result = leftOrder - rightOrder || left.start - right.start || left.end - right.end
        if (descending) result = -result
      }
    }
    return result || (left.id ?? '').localeCompare(right.id ?? '')
  })
}
