/**
 * Rows, labels, filters and chart specifications of the corpus overview (#254, #361); the
 * publication timeline is in `timeline.ts`.
 *
 * Every count is a number of documents. Rows keep the stored value (`key`) next to its
 * display label, so two codes with the same name (`ces`, `cze`: Czech) stay two rows. The
 * charts and the tables are drawn from the same rows.
 */
import type { VisualizationSpec } from 'vega-embed'
import type { CategoryDistribution, DocumentFilters } from 'src/generated/api'

export type RowKind = 'value' | 'other' | 'unknown'

export interface CategoryRow {
  key: string
  label: string
  count: number
  kind: RowKind
}

/** Names of the libraries most corpus documents come from; other codes are shown as stored. */
const LIBRARY_NAMES: Record<string, string> = {
  mzk: 'Moravian Library',
  nkp: 'National Library of the Czech Republic',
  knav: 'Library of the Czech Academy of Sciences'
}

let languageNames: Intl.DisplayNames | null | undefined

function languageName (code: string): string | undefined {
  if (languageNames === undefined) {
    try {
      languageNames = new Intl.DisplayNames(['en'], { type: 'language', fallback: 'none' })
    } catch {
      languageNames = null
    }
  }
  try {
    return languageNames?.of(code.trim()) ?? undefined
  } catch {
    return undefined // not a language code, e.g. a free-text value
  }
}

/** "Czech (ces)": the name when the code is a known language code, always with the code. */
export function languageLabel (code: string): string {
  const name = languageName(code)
  return name && name.toLowerCase() !== code.trim().toLowerCase() ? `${name} (${code})` : code
}

/** "Moravian Library (mzk)" for a known library code, otherwise the code as stored. */
export function libraryLabel (code: string): string {
  const name = LIBRARY_NAMES[code]
  return name ? `${name} (${code})` : code
}

export const OTHER_LABEL = 'Other values'
export const UNKNOWN_LABEL = 'Unknown'

/** One row per listed value, then "Other values" (if any) and "Unknown" (always). */
export function categoryRows (distribution: CategoryDistribution, label: (value: string) => string): CategoryRow[] {
  if (!distribution.available) return []
  const rows: CategoryRow[] = (distribution.values ?? []).map(v => ({ key: v.value, label: label(v.value), count: v.count, kind: 'value' }))
  if (distribution.otherCount) rows.push({ key: '\u0000other', label: OTHER_LABEL, count: distribution.otherCount, kind: 'other' })
  rows.push({ key: '\u0000unknown', label: UNKNOWN_LABEL, count: distribution.unknownCount ?? 0, kind: 'unknown' })
  return rows
}

export type FilterKey = 'years' | 'title' | 'libraries' | 'languages'
type ListKey = Exclude<FilterKey, 'years'>

/** One removable value of an applied filter; `value` is the list entry it stands for. */
export interface FilterChip {
  label: string
  value?: string
}

/** The applied values of one kind of filter; several values match any of them. */
export interface FilterGroup {
  key: FilterKey
  label: string
  chips: FilterChip[]
}

const LISTS: Record<ListKey, { field: 'titleContains' | 'libraries' | 'languages', label: string, name: (v: string) => string }> = {
  title: { field: 'titleContains', label: 'Title contains', name: (v) => v },
  libraries: { field: 'libraries', label: 'Library', name: libraryLabel },
  languages: { field: 'languages', label: 'Language', name: languageLabel }
}

/** True when the filters select every document. */
export function isUnfiltered (filters: DocumentFilters): boolean {
  return filterGroups(filters).length === 0
}

/** The applied filters by kind, in the order of the filter panel. */
export function filterGroups (filters: DocumentFilters): FilterGroup[] {
  const groups: FilterGroup[] = []
  const { yearMin, yearMax } = filters
  if (yearMin != null || yearMax != null) {
    const label = yearMin != null && yearMax != null
      ? (yearMin === yearMax ? `${yearMin}` : `${yearMin}–${yearMax}`)
      : (yearMin != null ? `from ${yearMin}` : `until ${yearMax}`)
    groups.push({ key: 'years', label: 'Years', chips: [{ label }] })
  }
  for (const [key, list] of Object.entries(LISTS) as [ListKey, typeof LISTS[ListKey]][]) {
    const values = filters[list.field] ?? []
    if (values.length) groups.push({ key, label: list.label, chips: values.map(value => ({ label: list.name(value), value })) })
  }
  return groups
}

/** The filters without one value of a list filter, or without the year range. */
export function withoutFilter (filters: DocumentFilters, key: FilterKey, value?: string): DocumentFilters {
  if (key === 'years') return { ...filters, yearMin: undefined, yearMax: undefined }
  const field = LISTS[key].field
  return { ...filters, [field]: (filters[field] ?? []).filter(v => v !== value) }
}

export interface Coverage {
  known: number
  unknown: number
  /** Share of documents with a known value, 0–100 (0 for an empty corpus). */
  percent: number
}

export function coverage (unknown: number, total: number): Coverage {
  const known = total - unknown
  return { known, unknown, percent: total > 0 ? Math.round((known / total) * 1000) / 10 : 0 }
}

const SCHEMA = 'https://vega.github.io/schema/vega-lite/v6.json'
/** Height of one bar row in pixels. */
const BAR_STEP = 22
const COLORS = { value: '#1976d2', other: '#78909c', unknown: '#b0bec5' }

/** Documents per value as horizontal bars in row order; Other and Unknown are named on the axis. */
export function categoryBarSpec (rows: CategoryRow[], title: string): VisualizationSpec {
  return {
    $schema: SCHEMA,
    data: { values: rows.map((row, order) => ({ ...row, order })) },
    // A fixed height (not a step): the chart is fitted to its container's width.
    height: Math.max(rows.length, 1) * BAR_STEP,
    mark: { type: 'bar', tooltip: true },
    encoding: {
      y: { field: 'label', type: 'nominal', title, sort: { field: 'order', order: 'ascending' }, axis: { labelLimit: 180 } },
      x: { field: 'count', type: 'quantitative', title: 'Documents', axis: { format: ',d', tickMinStep: 1 } },
      color: {
        field: 'kind',
        type: 'nominal',
        scale: { domain: ['value', 'other', 'unknown'], range: [COLORS.value, COLORS.other, COLORS.unknown] },
        legend: null
      },
      tooltip: [
        { field: 'label', type: 'nominal', title },
        { field: 'count', type: 'quantitative', title: 'Documents', format: ',d' }
      ]
    }
  }
}
