import { SearchType, type SearchFilter, type SearchFilterInput, type SearchRequest, type SearchVectorInfo } from 'src/generated/api'
import type { HistoryCriteria } from 'src/shared/searchHistory/history'
import { formatFilterLabel, intervalBounds, nominalLabel, type IntervalValue } from './searchFilters'

/**
 * What the Search page's history (#558) keeps of a search besides its query: a snapshot of
 * the fields of its `SearchRequest` that decide its results, in the request's own form.
 * Generated titles and summaries are deliberately left out, so running a search from the
 * history never spends the daily AI allowance by surprise. Each filter is a
 * `SearchFilterInput` with either chosen `values` or a `minValue`-`maxValue` range.
 */
export type SearchHistoryCriteria = Required<Pick<SearchRequest, 'type'>> & {
  vector: string | null
  userCollectionId: string | null
  filters: SearchFilterInput[]
}

/**
 * The format of {@link SearchHistoryCriteria} as stored. Raise it when what a stored
 * snapshot means changes, and convert or leave out older ones in `parseCriteria`; a tab
 * still running the previous version then asks the user to reload instead of reading them.
 */
export const SEARCH_CRITERIA_VERSION = 1

const MAX_ID_LENGTH = 200
const MAX_VALUES = 200
const SEARCH_TYPES: string[] = Object.values(SearchType)

const isId = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= MAX_ID_LENGTH
const optionalId = (value: unknown): string | null | undefined => (value === null ? null : isId(value) ? value : undefined)
const isBound = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)

/** The chosen values of a nominal filter, or null for a range. */
export function filterValuesOf (filter: SearchFilterInput): string[] | null {
  return Array.isArray(filter.values) ? (filter.values as string[]) : null
}

/** The range of an interval filter, or null for chosen values. */
export function filterRangeOf (filter: SearchFilterInput): { min: number, max: number } | null {
  return filter.values == null && isBound(filter.minValue) && isBound(filter.maxValue)
    ? { min: filter.minValue, max: filter.maxValue }
    : null
}

function parseFilter (raw: unknown): SearchFilterInput | null {
  if (typeof raw !== 'object' || raw === null) return null
  const { id, values, minValue, maxValue } = raw as Record<string, unknown>
  if (!isId(id)) return null
  if (Array.isArray(values)) {
    if (values.length === 0 || values.length > MAX_VALUES || !values.every(isId)) return null
    return { id, values: [...new Set(values)] }
  }
  if (values == null && isBound(minValue) && isBound(maxValue) && minValue <= maxValue) {
    return { id, minValue, maxValue }
  }
  return null
}

/** Stored criteria, validated (stored data is untrusted). Format 1 is the only one so far. */
function parseCriteria (raw: unknown, version: number): SearchHistoryCriteria | null {
  if (version !== SEARCH_CRITERIA_VERSION) return null
  if (typeof raw !== 'object' || raw === null) return null
  const { type, vector, userCollectionId, filters } = raw as Record<string, unknown>
  if (typeof type !== 'string' || !SEARCH_TYPES.includes(type)) return null
  const parsedVector = optionalId(vector)
  const parsedCollection = optionalId(userCollectionId)
  if (parsedVector === undefined || parsedCollection === undefined || !Array.isArray(filters)) return null
  const parsedFilters: SearchFilterInput[] = []
  for (const filter of filters as unknown[]) {
    const parsed = parseFilter(filter)
    if (!parsed || parsedFilters.some(f => f.id === parsed.id)) return null
    parsedFilters.push(parsed)
  }
  return { type: type as SearchType, vector: parsedVector, userCollectionId: parsedCollection, filters: parsedFilters }
}

/** Filters in a canonical order (by id, values sorted), so equal searches compare equal. */
function canonicalFilters (filters: SearchFilterInput[]): SearchFilterInput[] {
  return [...filters]
    .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
    .map((f) => {
      const values = filterValuesOf(f)
      return values ? { id: f.id, values: [...values].sort() } : { id: f.id, minValue: f.minValue, maxValue: f.maxValue }
    })
}

export const searchHistoryCriteria: HistoryCriteria<SearchHistoryCriteria> = {
  namespace: 'search',
  version: SEARCH_CRITERIA_VERSION,
  parse: parseCriteria,
  key: (c) => JSON.stringify([c.type, c.vector, c.userCollectionId, canonicalFilters(c.filters)])
}

/** The criteria of a search request as the Search page sends it. */
export function criteriaOfRequest (request: SearchRequest): SearchHistoryCriteria {
  const filters: SearchFilterInput[] = []
  for (const filter of request.filters ?? []) {
    const values = filterValuesOf(filter)
    const range = filterRangeOf(filter)
    if (values) {
      const kept = values.filter(isId)
      if (kept.length) filters.push({ id: filter.id, values: kept })
    } else if (range) {
      filters.push({ id: filter.id, minValue: range.min, maxValue: range.max })
    }
  }
  return {
    type: request.type ?? SearchType.hybrid,
    vector: request.vector ?? null,
    userCollectionId: request.userCollectionId ?? null,
    filters: canonicalFilters(filters)
  }
}

/** What the page currently offers, against which a stored search is restored. */
export interface SearchOptions {
  filters: SearchFilter[]
  vectors: SearchVectorInfo[]
  /** Collections the signed-in user may search (none when signed out). */
  collections: { id: string, name: string }[]
}

export interface RestoredSearch {
  type: SearchType
  vector: string | null
  userCollectionId: string | null
  /** Values for every offered filter: the stored ones, the others reset (full range, nothing chosen). */
  filterValues: Record<string, IntervalValue | string[]>
  /** Labels of the stored criteria that are no longer available and were left out. */
  dropped: string[]
}

/**
 * The page state that runs a stored search again. Criteria that are no longer offered (a
 * collection the user cannot read any more, a removed filter, value or search vector) are
 * left out and named in `dropped`. A stored range is limited to the filter's current
 * bounds; a range entirely outside them is left out.
 */
export function restoreSearch (criteria: SearchHistoryCriteria, options: SearchOptions): RestoredSearch {
  const dropped: string[] = []
  const filterValues: Record<string, IntervalValue | string[]> = {}
  for (const filter of options.filters) {
    if (filter.type === 'interval') filterValues[filter.id] = intervalBounds(filter)
    else if (filter.type === 'nominal') filterValues[filter.id] = []
  }

  let userCollectionId = criteria.userCollectionId
  if (userCollectionId && !options.collections.some(c => c.id === userCollectionId)) {
    dropped.push('Collection')
    userCollectionId = null
  }

  let vector = criteria.vector
  if (vector && !options.vectors.some(v => v.id === vector)) {
    dropped.push(`Embedding: ${vector}`)
    vector = null
  }

  for (const stored of criteria.filters) {
    const filter = options.filters.find(f => f.id === stored.id)
    const label = formatFilterLabel(stored.id)
    const values = filterValuesOf(stored)
    const range = filterRangeOf(stored)
    if (values) {
      if (filter?.type !== 'nominal') {
        dropped.push(label)
        continue
      }
      const known = new Set((filter.values ?? []).map(v => v.backendForm))
      const kept = values.filter(v => known.has(v))
      values.filter(v => !known.has(v)).forEach(v => dropped.push(`${label}: ${v}`))
      filterValues[filter.id] = kept
    } else if (range) {
      if (filter?.type !== 'interval') {
        dropped.push(label)
        continue
      }
      const bounds = intervalBounds(filter)
      const min = Math.max(range.min, bounds.min)
      const max = Math.min(range.max, bounds.max)
      if (min > max) {
        dropped.push(`${label}: ${range.min}-${range.max}`)
        continue
      }
      filterValues[filter.id] = { min, max }
    }
  }

  return { type: criteria.type, vector, userCollectionId, filterValues, dropped }
}

/**
 * A short description of a stored search's criteria besides its query, like the page's
 * active-filter chips: collection, chosen search vector and filters; empty without any.
 */
export function describeCriteria (criteria: SearchHistoryCriteria, options: SearchOptions): string {
  const parts: string[] = []
  if (criteria.userCollectionId) {
    const collection = options.collections.find(c => c.id === criteria.userCollectionId)
    parts.push(collection ? collection.name : 'Unavailable collection')
  }
  if (criteria.vector) {
    parts.push(`Embedding: ${options.vectors.find(v => v.id === criteria.vector)?.name ?? criteria.vector}`)
  }
  for (const stored of criteria.filters) {
    const label = formatFilterLabel(stored.id)
    const values = filterValuesOf(stored)
    const range = filterRangeOf(stored)
    if (values) {
      const filter = options.filters.find(f => f.id === stored.id)
      parts.push(`${label}: ${values.map(v => nominalLabel(filter, v)).join(', ')}`)
    } else if (range) {
      parts.push(`${label}: ${range.min}-${range.max}`)
    }
  }
  return parts.join(' · ')
}
