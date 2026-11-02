import { SearchType, type SearchFilter, type SearchRequest, type SearchVectorInfo } from 'src/generated/api'
import type { HistoryCriteria } from 'src/shared/searchHistory/history'
import { formatFilterLabel, intervalBounds, nominalLabel, type IntervalValue } from './searchFilters'

/** A stored filter: chosen values of a nominal filter or the range of an interval filter. */
export type StoredFilter =
  | { id: string, values: string[] }
  | { id: string, min: number, max: number }

/**
 * What the Search page's history (#558) keeps of a search besides its query: the criteria
 * that run it again. Generated titles and summaries are deliberately left out, so running a
 * search from the history never spends the daily AI allowance by surprise, and the
 * collection is kept by id only (its name is looked up when the list is shown).
 */
export interface SearchHistoryCriteria {
  type: SearchType
  /** Chosen search vector; null for the server's default. */
  vector: string | null
  collectionId: string | null
  filters: StoredFilter[]
}

const MAX_ID_LENGTH = 200
const MAX_VALUES = 200
const SEARCH_TYPES: string[] = Object.values(SearchType)

const isId = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= MAX_ID_LENGTH
const optionalId = (value: unknown): string | null | undefined => (value === null ? null : isId(value) ? value : undefined)

function parseFilter (raw: unknown): StoredFilter | null {
  if (typeof raw !== 'object' || raw === null) return null
  const { id, values, min, max } = raw as Record<string, unknown>
  if (!isId(id)) return null
  if (Array.isArray(values)) {
    if (values.length === 0 || values.length > MAX_VALUES || !values.every(isId)) return null
    return { id, values: [...new Set(values)] }
  }
  if (typeof min === 'number' && typeof max === 'number' && Number.isFinite(min) && Number.isFinite(max) && min <= max) {
    return { id, min, max }
  }
  return null
}

function parseCriteria (raw: unknown): SearchHistoryCriteria | null {
  if (typeof raw !== 'object' || raw === null) return null
  const { type, vector, collectionId, filters } = raw as Record<string, unknown>
  if (typeof type !== 'string' || !SEARCH_TYPES.includes(type)) return null
  const parsedVector = optionalId(vector)
  const parsedCollection = optionalId(collectionId)
  if (parsedVector === undefined || parsedCollection === undefined || !Array.isArray(filters)) return null
  const parsedFilters: StoredFilter[] = []
  for (const filter of filters as unknown[]) {
    const parsed = parseFilter(filter)
    if (!parsed || parsedFilters.some(f => f.id === parsed.id)) return null
    parsedFilters.push(parsed)
  }
  return { type: type as SearchType, vector: parsedVector, collectionId: parsedCollection, filters: parsedFilters }
}

/** Filters in a canonical order (by id, values sorted), so equal searches compare equal. */
function canonicalFilters (filters: StoredFilter[]): StoredFilter[] {
  return [...filters]
    .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
    .map(f => ('values' in f ? { id: f.id, values: [...f.values].sort() } : { id: f.id, min: f.min, max: f.max }))
}

export const searchHistoryCriteria: HistoryCriteria<SearchHistoryCriteria> = {
  namespace: 'search',
  parse: parseCriteria,
  key: (c) => JSON.stringify([c.type, c.vector, c.collectionId, canonicalFilters(c.filters)])
}

/** The criteria of a search request as the Search page sends it. */
export function criteriaOfRequest (request: SearchRequest): SearchHistoryCriteria {
  const filters: StoredFilter[] = []
  for (const filter of request.filters ?? []) {
    if (Array.isArray(filter.values)) {
      const values = (filter.values as unknown[]).filter(isId)
      if (values.length) filters.push({ id: filter.id, values })
    } else if (filter.minValue != null && filter.maxValue != null) {
      const min = Number(filter.minValue)
      const max = Number(filter.maxValue)
      if (Number.isFinite(min) && Number.isFinite(max)) filters.push({ id: filter.id, min, max })
    }
  }
  return {
    type: request.type ?? SearchType.hybrid,
    vector: request.vector ?? null,
    collectionId: request.userCollectionId ?? null,
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
  collectionId: string | null
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

  let collectionId = criteria.collectionId
  if (collectionId && !options.collections.some(c => c.id === collectionId)) {
    dropped.push('Collection')
    collectionId = null
  }

  let vector = criteria.vector
  if (vector && !options.vectors.some(v => v.id === vector)) {
    dropped.push(`Embedding: ${vector}`)
    vector = null
  }

  for (const stored of criteria.filters) {
    const filter = options.filters.find(f => f.id === stored.id)
    const label = formatFilterLabel(stored.id)
    if ('values' in stored) {
      if (filter?.type !== 'nominal') {
        dropped.push(label)
        continue
      }
      const known = new Set((filter.values ?? []).map(v => v.backendForm))
      const kept = stored.values.filter(v => known.has(v))
      stored.values.filter(v => !known.has(v)).forEach(v => dropped.push(`${label}: ${v}`))
      filterValues[filter.id] = kept
    } else {
      if (filter?.type !== 'interval') {
        dropped.push(label)
        continue
      }
      const bounds = intervalBounds(filter)
      const min = Math.max(stored.min, bounds.min)
      const max = Math.min(stored.max, bounds.max)
      if (min > max) {
        dropped.push(`${label}: ${stored.min}-${stored.max}`)
        continue
      }
      filterValues[filter.id] = { min, max }
    }
  }

  return { type: criteria.type, vector, collectionId, filterValues, dropped }
}

/**
 * A short description of a stored search's criteria besides its query, like the page's
 * active-filter chips: collection, chosen search vector and filters; empty without any.
 */
export function describeCriteria (criteria: SearchHistoryCriteria, options: SearchOptions): string {
  const parts: string[] = []
  if (criteria.collectionId) {
    const collection = options.collections.find(c => c.id === criteria.collectionId)
    parts.push(collection ? collection.name : 'Unavailable collection')
  }
  if (criteria.vector) {
    parts.push(`Embedding: ${options.vectors.find(v => v.id === criteria.vector)?.name ?? criteria.vector}`)
  }
  for (const stored of criteria.filters) {
    const label = formatFilterLabel(stored.id)
    if ('values' in stored) {
      const filter = options.filters.find(f => f.id === stored.id)
      parts.push(`${label}: ${stored.values.map(v => nominalLabel(filter, v)).join(', ')}`)
    } else {
      parts.push(`${label}: ${stored.min}-${stored.max}`)
    }
  }
  return parts.join(' · ')
}
