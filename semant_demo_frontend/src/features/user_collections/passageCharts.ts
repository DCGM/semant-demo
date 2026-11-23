import { CollectionPassagesRequestDimensionEnum, type CollectionPassages, type PassageClassification, type SearchFilter } from 'src/generated/api'
import { categoryRows, languageLabel, type CategoryRow } from 'src/features/analytics/corpusOverview'
import { humanizeName } from 'src/features/search/classifications'
import type { PassageDimension } from './useUserCollectionsRepository'

// The charts of a collection's included passages on its Overview tab (#807, 622c of #622): rows
// for `CategoryChart` from `POST /api/analytics/collection/passages`, and the classifications
// the selector offers. Counts are passages, never documents; the charts are not clickable.

/** The classification shown first: the most varied one in production collections (#807). */
export const PREFERRED_DIMENSION: PassageDimension = 'subject_domain'
export const WITHOUT_VALUE_LABEL = 'Without a value'

const DIMENSIONS = new Set<string>(Object.values(CollectionPassagesRequestDimensionEnum))

export interface DimensionOption {
  value: PassageDimension
  label: string
}

/**
 * The filter of each classification the search filters configure: a nominal filter with values
 * on a chunk classification, the last one when several target it, as the backend's
 * `chunk_vocabulary` takes the values from it. In the order the classifications first appear.
 */
export function classificationFilters (filters: readonly SearchFilter[]): Map<PassageDimension, SearchFilter> {
  const byDimension = new Map<PassageDimension, SearchFilter>()
  for (const filter of filters) {
    if (filter.type !== 'nominal' || !filter.values?.length || !DIMENSIONS.has(filter.targetProperty)) continue
    byDimension.set(filter.targetProperty as PassageDimension, filter)
  }
  return byDimension
}

/**
 * The classifications offered (`classificationFilters`): `subject_domain` first, then in the
 * filters' order, each named by its filter.
 */
export function dimensionOptions (filters: readonly SearchFilter[]): DimensionOption[] {
  const options: DimensionOption[] = [...classificationFilters(filters)].map(([dimension, filter]) =>
    ({ value: dimension, label: filter.name || humanizeName(dimension) }))
  const preferred = options.findIndex(o => o.value === PREFERRED_DIMENSION)
  if (preferred > 0) options.unshift(...options.splice(preferred, 1))
  return options
}

/** The answer describes this collection's passages (`scope`, `userCollectionId`). */
export const ofCollection = (passages: CollectionPassages, collectionId: string) =>
  passages.scope === 'user_collection' && passages.userCollectionId === collectionId

/** Passages per detected language: one row per listed language, then Other and Unknown. */
export function languageRows (passages: CollectionPassages): CategoryRow[] {
  return passages.languages ? categoryRows(passages.languages, languageLabel) : []
}

export interface ClassificationChart {
  rows: CategoryRow[]
  /** Configured values some passage holds, and all configured values. */
  occurring: number
  configured: number
  /** "Without a value" is approximate: a value outside the vocabulary is stored. */
  approximate: boolean
}

/**
 * The rows of one classification: the values some passage holds (configured values in
 * vocabulary order, named by the search filter as on result badges, then stored values outside
 * the vocabulary under their raw name, marked as not configured), then "Without a value".
 * Configured values no passage holds are left out of the bars and counted in `occurring` /
 * `configured` instead. Every label is distinct (a repeated one gets the stored value added):
 * the bars are drawn per label, so two values with one label would merge into one bar. Null when
 * the store does not record the classification.
 */
export function classificationChart (classification: PassageClassification,
  filter: SearchFilter | undefined): ClassificationChart | null {
  if (!classification.available) return null
  const values = classification.values ?? []
  const label = (value: string) => filter?.values?.find(v => v.backendForm === value)?.userForm || humanizeName(value)
  const rows: CategoryRow[] = values.filter(v => v.count > 0).map(v => ({
    key: v.value, label: v.configured ? label(v.value) : `${v.value} (not configured)`, count: v.count, kind: 'value'
  }))
  const uses = new Map<string, number>()
  for (const row of rows) uses.set(row.label, (uses.get(row.label) ?? 0) + 1)
  for (const row of rows) if ((uses.get(row.label) ?? 0) > 1) row.label = `${row.label} (${row.key})`
  rows.push({ key: '\u0000unknown', label: WITHOUT_VALUE_LABEL, count: classification.withoutValueCount ?? 0, kind: 'unknown' })
  const configured = values.filter(v => v.configured)
  return {
    rows,
    occurring: configured.filter(v => v.count > 0).length,
    configured: configured.length,
    approximate: !!classification.withoutValueApproximate
  }
}
