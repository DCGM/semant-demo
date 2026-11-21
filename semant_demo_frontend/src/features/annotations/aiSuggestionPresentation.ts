import type { TagSpan } from 'src/generated/api'

/** Panel-only presentation; the shared pending list keeps its gutter ordering. */
export type ProposalSort = 'confidence' | 'document' | 'explanation' | 'created' | 'distance'

/** Approximate position of the reader viewport in the document. */
export interface ProposalTextPosition { chunkId: string; charOffset: number }

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

const createdAtFormatter = new Intl.DateTimeFormat(undefined, {
  year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
})

/** Show recorded provenance in the reader's local time; never invent a timestamp. */
export function formatSuggestionCreatedAt(span: TagSpan): string {
  const time = getCreatedTime(span)
  return time === null ? 'Date unavailable' : createdAtFormatter.format(time)
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

/** Use the canonical chunk order plus a fraction of its text length for local distance. */
function positionOf (
  chunkId: string, offset: number, order: ReadonlyMap<string, number>,
  lengths: ReadonlyMap<string, number>
): number | null {
  const chunkIndex = order.get(chunkId)
  if (chunkIndex === undefined) return null
  const length = Math.max(1, lengths.get(chunkId) ?? 1)
  return chunkIndex + Math.max(0, Math.min(1, offset / length))
}

/** Pure, deterministic selector, with AND filters and stable ID ties. */
export function filterAndSortSuggestions<T extends WithSpan>(
  entries: readonly T[], filters: ProposalFilters, sort: ProposalSort,
  descending: boolean, chunkOrder: ReadonlyMap<string, number>,
  readerPosition: ProposalTextPosition | null = null,
  chunkLengths: ReadonlyMap<string, number> = new Map()
): T[] {
  const query = filters.reason.trim().toLocaleLowerCase()
  const readerAt = readerPosition
    ? positionOf(readerPosition.chunkId, readerPosition.charOffset, chunkOrder, chunkLengths)
    : null
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
    } else if (sort === 'distance') {
      const leftAt = positionOf(left.chunkId, left.start, chunkOrder, chunkLengths)
      const rightAt = positionOf(right.chunkId, right.start, chunkOrder, chunkLengths)
      result = compareNullable(
        leftAt === null || readerAt === null ? null : Math.abs(leftAt - readerAt),
        rightAt === null || readerAt === null ? null : Math.abs(rightAt - readerAt),
        (x, y) => x - y, descending
      )
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
