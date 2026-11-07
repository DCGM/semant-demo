import type { SearchFilter, SearchFilterInput } from 'src/generated/api'
import { normalizeCriteria, type Criteria } from 'src/features/explore/criteria'

/** Range of an interval filter's slider, from the bounds the server reports. */
export interface IntervalValue {
  min: number
  max: number
}

/** `publication_year` -> `Publication Year`: the label of a search filter. */
export function formatFilterLabel (id: string): string {
  return id
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

/** Range of an interval filter (the generated client types its numeric bounds loosely). */
export function intervalBounds (filter: SearchFilter): IntervalValue {
  const min = filter.minValue != null ? Math.floor(Number(filter.minValue)) : 1800
  const max = filter.maxValue != null ? Math.ceil(Number(filter.maxValue)) : 2026
  return { min, max }
}

/** Shown label of a nominal filter value; the value itself when the filter does not list it. */
export function nominalLabel (filter: SearchFilter | undefined, value: string): string {
  return filter?.values?.find(v => v.backendForm === value || v.userForm === value)?.userForm ?? value
}

/// /////////////////////////////////////////
// Configured filters and search criteria //
/// /////////////////////////////////////////

// The page offers the configured search filters (`GET /api/search/filters`) as widgets that
// edit the shared search criteria (#605, `features/explore/criteria.ts`): the year range is
// the document filter on the publication year (the chunks' copy, as before), the language
// filter the passage language, the other nominal filters the passage classifications, by
// their stored property name (`target_property`, as `search/filters.chunk_vocabulary`).

const YEAR_PROPERTY = 'yearIssued'
const LANGUAGE_PROPERTY = 'language'

/** Which part of the criteria a configured filter edits; null for one the page cannot apply. */
export type FilterTarget =
  | { kind: 'year' }
  | { kind: 'chunkLanguage' }
  | { kind: 'classification', name: string }

export function filterTarget (filter: SearchFilter): FilterTarget | null {
  if (filter.type === 'interval') return filter.targetProperty === YEAR_PROPERTY ? { kind: 'year' } : null
  if (filter.type !== 'nominal' || !filter.values?.length) return null
  if (filter.targetProperty === LANGUAGE_PROPERTY) return { kind: 'chunkLanguage' }
  return { kind: 'classification', name: filter.targetProperty }
}

/** The year range shown by an interval filter: the criteria's years, open ends at its bounds. */
export function yearRangeOf (criteria: Criteria, filter: SearchFilter): IntervalValue {
  const bounds = intervalBounds(filter)
  const clamp = (year: number) => Math.min(Math.max(year, bounds.min), bounds.max)
  return {
    min: criteria.documentFilters.yearMin === null ? bounds.min : clamp(criteria.documentFilters.yearMin),
    max: criteria.documentFilters.yearMax === null ? bounds.max : clamp(criteria.documentFilters.yearMax)
  }
}

/** The criteria with the chosen year range; an end at the filter's bound leaves that end open. */
export function withYearRange (criteria: Criteria, filter: SearchFilter, range: IntervalValue): Criteria {
  const bounds = intervalBounds(filter)
  return normalizeCriteria({
    ...criteria,
    documentFilters: {
      ...criteria.documentFilters,
      yearMin: range.min <= bounds.min ? null : range.min,
      yearMax: range.max >= bounds.max ? null : range.max
    }
  })
}

/** The values a nominal filter has chosen in the criteria. */
export function nominalValuesOf (criteria: Criteria, filter: SearchFilter): string[] {
  const target = filterTarget(filter)
  if (target?.kind === 'chunkLanguage') return criteria.chunkFilters.languages
  if (target?.kind === 'classification') return criteria.chunkFilters.classifications[target.name] ?? []
  return []
}

export function withNominalValues (criteria: Criteria, filter: SearchFilter, values: readonly string[] | null): Criteria {
  const target = filterTarget(filter)
  const chosen = [...(values ?? [])]
  if (target?.kind === 'chunkLanguage') {
    return normalizeCriteria({ ...criteria, chunkFilters: { ...criteria.chunkFilters, languages: chosen } })
  }
  if (target?.kind === 'classification') {
    const classifications = { ...criteria.chunkFilters.classifications, [target.name]: chosen }
    return normalizeCriteria({ ...criteria, chunkFilters: { ...criteria.chunkFilters, classifications } })
  }
  return criteria
}

/**
 * The criteria restricted to the passage filters the page offers, in their configured
 * spelling (compared ignoring case, as the server does); the others are left out and named in
 * `dropped`. Document filters are kept: the server checks them.
 */
export function offeredCriteria (criteria: Criteria, filters: SearchFilter[]): { criteria: Criteria, dropped: string[] } {
  const dropped: string[] = []
  const pick = (label: string, chosen: string[], filter: SearchFilter | undefined): string[] => {
    const byKey = new Map((filter?.values ?? []).map(v => [v.backendForm.toLowerCase(), v.backendForm]))
    const kept: string[] = []
    for (const value of chosen) {
      const known = byKey.get(value.toLowerCase())
      if (known) kept.push(known)
      else dropped.push(`${label}: ${value}`)
    }
    return kept
  }
  const languageFilter = filters.find(f => filterTarget(f)?.kind === 'chunkLanguage')
  const languages = pick('Passage language', criteria.chunkFilters.languages, languageFilter)
  const classifications: Record<string, string[]> = {}
  for (const [name, chosen] of Object.entries(criteria.chunkFilters.classifications)) {
    const filter = filters.find(f => { const t = filterTarget(f); return t?.kind === 'classification' && t.name === name })
    classifications[name] = pick(formatFilterLabel(name), chosen, filter)
  }
  return { criteria: normalizeCriteria({ ...criteria, chunkFilters: { languages, classifications } }), dropped }
}

/** The criteria of a search restored from the history: its query and the filter values of `restoreSearch`. */
export function criteriaOfFilterValues (
  textQuery: string, values: Record<string, IntervalValue | string[]>, filters: SearchFilter[]
): Criteria {
  let criteria = normalizeCriteria({ textQuery })
  for (const filter of filters) {
    const value = values[filter.id]
    if (value === undefined) continue
    if (filterTarget(filter)?.kind === 'year' && !Array.isArray(value)) criteria = withYearRange(criteria, filter, value)
    else if (Array.isArray(value)) criteria = withNominalValues(criteria, filter, value)
  }
  return criteria
}

/**
 * The filters of the criteria as the search history keeps them (#558, `SearchFilterInput`
 * by configured filter id). Document filters the page has no widget for (titles, libraries,
 * document languages) cannot be kept there and are left out.
 */
export function historyFiltersOf (criteria: Criteria, filters: SearchFilter[]): SearchFilterInput[] {
  const kept: SearchFilterInput[] = []
  for (const filter of filters) {
    const target = filterTarget(filter)
    if (target?.kind === 'year') {
      if (criteria.documentFilters.yearMin === null && criteria.documentFilters.yearMax === null) continue
      const range = yearRangeOf(criteria, filter)
      kept.push({ id: filter.id, minValue: range.min, maxValue: range.max })
    } else if (target) {
      const chosen = nominalValuesOf(criteria, filter)
      if (chosen.length) kept.push({ id: filter.id, values: [...chosen] })
    }
  }
  return kept
}

/** An applied criterion shown as a removable chip; `without` is the criteria without it. */
export interface CriterionChip {
  key: string
  icon: string
  label: string
  without: Criteria
}

/** Chips of the criteria's filters (not the text query), labelled with the configured names. */
export function criteriaChips (criteria: Criteria, filters: SearchFilter[]): CriterionChip[] {
  const chips: CriterionChip[] = []
  const d = criteria.documentFilters
  const yearFilter = filters.find(f => filterTarget(f)?.kind === 'year')
  if (d.yearMin !== null || d.yearMax !== null) {
    const label = yearFilter ? formatFilterLabel(yearFilter.id) : 'Publication year'
    const range = d.yearMin !== null && d.yearMax !== null ? `${d.yearMin}-${d.yearMax}` : d.yearMin !== null ? `from ${d.yearMin}` : `to ${d.yearMax}`
    chips.push({ key: 'year', icon: 'event', label: `${label}: ${range}`, without: normalizeCriteria({ ...criteria, documentFilters: { ...d, yearMin: null, yearMax: null } }) })
  }
  const listChips = (field: 'titleContains' | 'libraries' | 'languages', label: string, icon: string) => {
    for (const value of d[field]) {
      chips.push({ key: `${field}:${value}`, icon, label: `${label}: ${value}`, without: normalizeCriteria({ ...criteria, documentFilters: { ...d, [field]: d[field].filter(v => v !== value) } }) })
    }
  }
  listChips('titleContains', 'Title', 'title')
  listChips('libraries', 'Library', 'account_balance')
  listChips('languages', 'Document language', 'translate')

  const c = criteria.chunkFilters
  const languageFilter = filters.find(f => filterTarget(f)?.kind === 'chunkLanguage')
  for (const value of c.languages) {
    chips.push({
      key: `chunk_languages:${value}`,
      icon: 'language',
      label: `${languageFilter ? formatFilterLabel(languageFilter.id) : 'Passage language'}: ${nominalLabel(languageFilter, value)}`,
      without: normalizeCriteria({ ...criteria, chunkFilters: { ...c, languages: c.languages.filter(v => v !== value) } })
    })
  }
  for (const [name, chosen] of Object.entries(c.classifications)) {
    const filter = filters.find(f => { const t = filterTarget(f); return t?.kind === 'classification' && t.name === name })
    for (const value of chosen) {
      chips.push({
        key: `chunk_classifications:${name}:${value}`,
        icon: 'filter_list',
        label: `${formatFilterLabel(filter?.id ?? name)}: ${nominalLabel(filter, value)}`,
        without: normalizeCriteria({ ...criteria, chunkFilters: { ...c, classifications: { ...c.classifications, [name]: chosen.filter(v => v !== value) } } })
      })
    }
  }
  return chips
}
