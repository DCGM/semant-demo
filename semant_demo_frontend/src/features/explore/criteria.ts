import type { LocationQuery, LocationQueryRaw } from 'vue-router'
import type { SearchCriteria } from 'src/generated/api'

/**
 * The search criteria of Explore (docs/EXPLORATION.md, #605): an optional text query with
 * document filters and chunk ("passage") filters, as the backend's `SearchCriteria`, and how
 * applied criteria, the results mode, the view and the search vector are kept in the URL.
 *
 * `Criteria` is always canonical (`normalizeCriteria`): lists trimmed, de-duplicated and
 * sorted, a blank text query `null`, so two equal criteria have the same `criteriaKey`. The
 * server validates them again; this module only keeps malformed URL values out.
 */

export type ResultsMode = 'documents' | 'passages'
export type ExploreView = 'results' | 'visualizations'

export const RESULTS_MODES: readonly ResultsMode[] = ['documents', 'passages']
export const EXPLORE_VIEWS: readonly ExploreView[] = ['results', 'visualizations']

export interface DocumentCriteria {
  yearMin: number | null
  yearMax: number | null
  titleContains: string[]
  libraries: string[]
  /** `Documents.language`, not the language of a passage. */
  languages: string[]
}

export interface ChunkCriteria {
  /** `Chunks.language`: the language of the passage itself. */
  languages: string[]
  /** Configured classification (stored property name) -> accepted values. */
  classifications: Record<string, string[]>
}

export interface Criteria {
  textQuery: string | null
  documentFilters: DocumentCriteria
  chunkFilters: ChunkCriteria
}

/** Limits of `features/documents/criteria.py`, checked here only to refuse malformed URLs. */
export const MAX_TEXT_QUERY_LENGTH = 1000
const MAX_VALUE_LENGTH = 100
const MAX_VALUES = 50
const MAX_TITLES = 10
const MAX_ID_LENGTH = 200
const CLASSIFICATION_SEPARATOR = ':'

export function emptyCriteria (): Criteria {
  return {
    textQuery: null,
    documentFilters: { yearMin: null, yearMax: null, titleContains: [], libraries: [], languages: [] },
    chunkFilters: { languages: [], classifications: {} }
  }
}

const values = (list: readonly string[] | undefined | null): string[] =>
  [...new Set((list ?? []).map(v => v.trim()).filter(v => v !== ''))].sort()

/** Criteria in canonical form; missing parts are empty. */
export function normalizeCriteria (criteria: {
  textQuery?: string | null
  documentFilters?: Partial<DocumentCriteria> | null
  chunkFilters?: Partial<ChunkCriteria> | null
}): Criteria {
  const documents = criteria.documentFilters ?? {}
  const chunks = criteria.chunkFilters ?? {}
  const classifications: Record<string, string[]> = {}
  for (const name of Object.keys(chunks.classifications ?? {}).map(n => n.trim()).sort()) {
    const chosen = values(chunks.classifications?.[name])
    if (name && chosen.length) classifications[name] = chosen
  }
  return {
    textQuery: criteria.textQuery?.trim() || null,
    documentFilters: {
      yearMin: documents.yearMin ?? null,
      yearMax: documents.yearMax ?? null,
      titleContains: values(documents.titleContains),
      libraries: values(documents.libraries),
      languages: values(documents.languages)
    },
    chunkFilters: { languages: values(chunks.languages), classifications }
  }
}

export function criteriaKey (criteria: Criteria): string {
  return JSON.stringify(normalizeCriteria(criteria))
}

export function sameCriteria (a: Criteria, b: Criteria): boolean {
  return criteriaKey(a) === criteriaKey(b)
}

/** Whether any document or chunk filter is set (the text query aside). */
export function hasFilters (criteria: Criteria): boolean {
  const d = criteria.documentFilters
  const c = criteria.chunkFilters
  return d.yearMin !== null || d.yearMax !== null || d.titleContains.length > 0 || d.libraries.length > 0 ||
    d.languages.length > 0 || c.languages.length > 0 || Object.keys(c.classifications).length > 0
}

/** The request form of the criteria. */
export function toSearchCriteria (criteria: Criteria): SearchCriteria {
  const c = normalizeCriteria(criteria)
  return { textQuery: c.textQuery, documentFilters: c.documentFilters, chunkFilters: c.chunkFilters }
}

/** Criteria from the backend's (normalized) echo. */
export function fromSearchCriteria (criteria: SearchCriteria): Criteria {
  return normalizeCriteria(criteria)
}

/// //////
// URL //
/// //////

/**
 * What an Explore URL holds: the applied criteria, the results mode and view when chosen
 * explicitly (`null`: the default), and the selected search vector (`null`: the server's
 * default). Nothing private: user collections are never part of it.
 */
export interface ExploreLocation {
  criteria: Criteria
  mode: ResultsMode | null
  view: ExploreView | null
  vector: string | null
}

export function emptyLocation (): ExploreLocation {
  return { criteria: emptyCriteria(), mode: null, view: null, vector: null }
}

export function locationKey (location: ExploreLocation): string {
  return JSON.stringify([criteriaKey(location.criteria), location.mode, location.view, location.vector])
}

/** The results mode shown: the chosen one, otherwise Passages for a text query and Documents without. */
export function effectiveMode (location: ExploreLocation): ResultsMode {
  return location.mode ?? (location.criteria.textQuery ? 'passages' : 'documents')
}

/**
 * Query parameters of the URL. The filter names are those of document browsing
 * (`GET /api/documents/browse`); `q` is the text query. Empty values are left out, so the
 * URL of the empty criteria has no parameters.
 */
export function locationQuery (location: ExploreLocation): LocationQueryRaw {
  const c = normalizeCriteria(location.criteria)
  const query: LocationQueryRaw = {}
  if (c.textQuery) query.q = c.textQuery
  if (c.documentFilters.yearMin !== null) query.year_min = String(c.documentFilters.yearMin)
  if (c.documentFilters.yearMax !== null) query.year_max = String(c.documentFilters.yearMax)
  if (c.documentFilters.titleContains.length) query.title_contains = c.documentFilters.titleContains
  if (c.documentFilters.libraries.length) query.libraries = c.documentFilters.libraries
  if (c.documentFilters.languages.length) query.languages = c.documentFilters.languages
  if (c.chunkFilters.languages.length) query.chunk_languages = c.chunkFilters.languages
  const classified = Object.entries(c.chunkFilters.classifications)
    .flatMap(([name, chosen]) => chosen.map(value => `${name}${CLASSIFICATION_SEPARATOR}${value}`))
  if (classified.length) query.chunk_classifications = classified
  if (location.mode) query.mode = location.mode
  if (location.view) query.view = location.view
  if (location.vector) query.vector = location.vector
  return query
}

export interface ParsedLocation {
  location: ExploreLocation
  /** Descriptions of the URL values that were malformed and left out. */
  invalid: string[]
}

const asList = (raw: LocationQuery[string] | undefined): string[] =>
  (Array.isArray(raw) ? raw : raw == null ? [] : [raw]).filter((v): v is string => v !== null)

/**
 * The location an Explore URL describes. Malformed values (a year that is not a year, too
 * many or too long values, an unknown mode) are left out and named in `invalid`; parameters
 * Explore does not use are ignored. Whether a value is offered (a configured classification,
 * a search vector) is checked by the page against what it loaded.
 */
export function parseLocationQuery (query: LocationQuery, now: Date = new Date()): ParsedLocation {
  const invalid: string[] = []
  const location = emptyLocation()
  const criteria = location.criteria

  const single = (name: string, label: string): string | null => {
    const list = asList(query[name])
    if (list.length > 1) {
      invalid.push(`${label} (given more than once)`)
      return null
    }
    return list[0] ?? null
  }
  const list = (name: string, label: string, max = MAX_VALUES): string[] => {
    const raw = asList(query[name]).map(v => v.trim()).filter(v => v !== '')
    if (raw.length > max || raw.some(v => v.length > MAX_VALUE_LENGTH)) {
      invalid.push(label)
      return []
    }
    return raw
  }
  const year = (name: string, label: string): number | null => {
    const raw = single(name, label)
    if (raw === null) return null
    const value = /^\d{1,4}$/.test(raw.trim()) ? Number(raw.trim()) : NaN
    if (!Number.isInteger(value) || value < 1 || value > now.getFullYear()) {
      invalid.push(`${label}: ${raw}`)
      return null
    }
    return value
  }

  const text = single('q', 'Text query')
  if (text !== null && text.length > MAX_TEXT_QUERY_LENGTH) invalid.push('Text query (too long)')
  else criteria.textQuery = text

  const yearMin = year('year_min', 'Publication year from')
  const yearMax = year('year_max', 'Publication year to')
  if (yearMin !== null && yearMax !== null && yearMin > yearMax) {
    invalid.push(`Publication years ${yearMin}–${yearMax}`)
  } else {
    criteria.documentFilters.yearMin = yearMin
    criteria.documentFilters.yearMax = yearMax
  }
  criteria.documentFilters.titleContains = list('title_contains', 'Title', MAX_TITLES)
  criteria.documentFilters.libraries = list('libraries', 'Library')
  criteria.documentFilters.languages = list('languages', 'Document language')
  criteria.chunkFilters.languages = list('chunk_languages', 'Passage language')

  for (const item of asList(query.chunk_classifications)) {
    const at = item.indexOf(CLASSIFICATION_SEPARATOR)
    const name = at > 0 ? item.slice(0, at).trim() : ''
    const value = at > 0 ? item.slice(at + 1).trim() : ''
    if (!name || !value || value.length > MAX_VALUE_LENGTH || name.length > MAX_VALUE_LENGTH) {
      invalid.push(`Passage filter: ${item}`)
      continue
    }
    const chosen = (criteria.chunkFilters.classifications[name] ??= [])
    if (chosen.length >= MAX_VALUES) invalid.push(`Passage filter: ${item}`)
    else chosen.push(value)
  }

  const mode = single('mode', 'Results mode')
  if (mode !== null) {
    if ((RESULTS_MODES as readonly string[]).includes(mode)) location.mode = mode as ResultsMode
    else invalid.push(`Results mode: ${mode}`)
  }
  const view = single('view', 'View')
  if (view !== null) {
    if ((EXPLORE_VIEWS as readonly string[]).includes(view)) location.view = view as ExploreView
    else invalid.push(`View: ${view}`)
  }
  const vector = single('vector', 'Embedding model')
  if (vector !== null) {
    if (vector.trim() && vector.length <= MAX_ID_LENGTH) location.vector = vector.trim()
    else invalid.push('Embedding model')
  }

  location.criteria = normalizeCriteria(criteria)
  return { location, invalid }
}
