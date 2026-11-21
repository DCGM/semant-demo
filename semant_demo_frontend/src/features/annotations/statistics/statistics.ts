import { SpanType, type AnnotatedDocument, type AnnotationFacets, type AnnotationFacetsRequest, type Facet, type Tag } from 'src/generated/api'
import { languageLabel, libraryLabel } from 'src/features/analytics/corpusOverview'
import { annotationFilters, ranking, type ConcordanceFilters } from '../concordance/concordanceStore'

/**
 * The statistics of the workspace's annotation query (#818): the facet counts of #667 over exactly
 * the query's own population (`selfExclusion: false`), so every distribution counts the same
 * annotations and names them, and each category leads to the KWIC with exactly those annotations.
 */

/** The distributions, in the order shown. */
export const DIMENSIONS = ['type', 'tag', 'year', 'document', 'library', 'language'] as const
export type Dimension = typeof DIMENSIONS[number]

export const DIMENSION_LABELS: Record<Dimension, string> = {
  type: 'Status',
  tag: 'Tag',
  year: 'Publication year',
  document: 'Source document',
  library: 'Library',
  language: 'Document language'
}

export const STATUS_LABELS: Record<SpanType, string> = {
  [SpanType.pos]: 'Confirmed',
  [SpanType.auto]: 'Proposals',
  [SpanType.neg]: 'Rejected'
}

/** The order of the status choices and rows. */
export const STATUS_ORDER: SpanType[] = [SpanType.pos, SpanType.auto, SpanType.neg]

/** What the Missing row of a dimension means. */
const MISSING_LABELS: Record<Dimension, string> = {
  type: 'No status',
  tag: 'No tag',
  year: 'Unknown year',
  document: 'No source document',
  library: 'Unknown library',
  language: 'Unknown language'
}

/** The facet request of the statistics of `f`: the query itself, every facet over its own population. */
export function statisticsRequest (f: ConcordanceFilters): AnnotationFacetsRequest {
  return { ...annotationFilters(f), ranking: ranking(f), facets: [...DIMENSIONS], selfExclusion: false }
}

/** One row of a distribution: a value, or the annotations without one (`missing`). */
export interface DistributionRow {
  key: string
  label: string
  count: number
  /** `count` of the distribution's total (0..1); 0 when the total is 0. */
  share: number
  kind: 'value' | 'missing'
  /** The filter change that lists exactly these annotations in the KWIC; null when there is none
   * (Missing rows, ranked scopes). */
  drill: Partial<ConcordanceFilters> | null
}

/** The labels of the values of each dimension. */
export interface Labels {
  tags: Tag[]
  documents: AnnotatedDocument[]
}

export function valueLabel (dimension: Dimension, value: string, labels: Labels): string {
  switch (dimension) {
    case 'type': return STATUS_LABELS[value as SpanType] ?? value
    case 'tag': return labels.tags.find(t => t.id === value)?.name ?? 'Unknown tag'
    case 'document': {
      const document = labels.documents.find(d => d.id === value)
      if (!document) return 'Source document'
      return document.available ? (document.title || 'Untitled document') : 'Unavailable source'
    }
    case 'library': return libraryLabel(value)
    case 'language': return languageLabel(value)
    default: return value
  }
}

/**
 * The filter change that lists exactly the annotations of `value` of a lexical query `f`: the
 * dimension's filter narrowed to that one value. The query's own filter on the dimension (if any)
 * includes the value, as it was counted, so the narrowed query is the query AND the value.
 */
export function drillChange (dimension: Dimension, value: string, f: ConcordanceFilters): Partial<ConcordanceFilters> {
  const documents = f.documentFilters
  switch (dimension) {
    case 'type': return { types: [value as SpanType] }
    case 'tag': return { tagIds: [value] }
    case 'document': return { documentIds: [value] }
    case 'year': return { documentFilters: { ...documents, yearMin: Number(value), yearMax: Number(value) } }
    case 'library': return { documentFilters: { ...documents, libraries: [value] } }
    case 'language': return { documentFilters: { ...documents, languages: [value] } }
  }
}

/** The rows of one distribution: its values (statuses in their fixed order, years in time order,
 * the others most annotations first), then the Missing row when any annotation has no value. */
export function distributionRows (facet: Facet, dimension: Dimension, labels: Labels,
  f: ConcordanceFilters, drillable: boolean): DistributionRow[] {
  const share = (n: number) => (facet.total ? n / facet.total : 0)
  const values = [...facet.values]
  if (dimension === 'type') values.sort((a, b) => STATUS_ORDER.indexOf(a.value as SpanType) - STATUS_ORDER.indexOf(b.value as SpanType))
  if (dimension === 'year') values.sort((a, b) => Number(a.value) - Number(b.value))
  const rows: DistributionRow[] = values.map(v => ({
    key: v.value,
    label: valueLabel(dimension, v.value, labels),
    count: v.count,
    share: share(v.count),
    kind: 'value',
    drill: drillable ? drillChange(dimension, v.value, f) : null
  }))
  if (facet.missing > 0) {
    rows.push({ key: '__missing__', label: MISSING_LABELS[dimension], count: facet.missing, share: share(facet.missing), kind: 'missing', drill: null })
  }
  return rows
}

/** The facet of `dimension`, or null when the server left it out (it could not be counted). */
export function facetOf (statistics: AnnotationFacets | null, dimension: Dimension): Facet | null {
  return statistics?.facets.find(f => f.facet === dimension) ?? null
}

/** Whether the counts are of a ranked top k rather than every match. */
export function isTopK (statistics: AnnotationFacets | null): boolean {
  return statistics?.population === 'top_k'
}

const numberFormat = new Intl.NumberFormat('en')
export const formatCount = (n: number) => numberFormat.format(n)

/** A share as a percentage with one decimal (none for 0 and 100 %). */
export function formatShare (share: number): string {
  const percent = share * 100
  if (percent === 0 || percent === 100) return `${percent} %`
  if (percent < 0.1) return '<0.1 %'
  return `${percent.toFixed(1)} %`
}

/** The denominator every share of the statistics is of, said in words. */
export function denominatorText (statistics: AnnotationFacets, total: number): string {
  const n = formatCount(total)
  if (isTopK(statistics)) return `of the ${n} annotations retrieved in the top ${statistics.k ?? total} — not the whole collection`
  return `of all ${n} annotations matching the query`
}

/** How many rows a distribution's card shows; its detail lists all of them. */
export const CARD_ROWS = 8

export type RowOrder = 'count' | 'value'

/** The rows in `order`: most annotations first, or by value (statuses in their order, years in
 * time order, names alphabetically); the Missing row always last. */
export function orderedRows (rows: DistributionRow[], dimension: Dimension, order: RowOrder): DistributionRow[] {
  const values = rows.filter(r => r.kind === 'value')
  const missing = rows.filter(r => r.kind === 'missing')
  const sorted = [...values]
  if (order === 'count') sorted.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
  else if (dimension === 'type') sorted.sort((a, b) => STATUS_ORDER.indexOf(a.key as SpanType) - STATUS_ORDER.indexOf(b.key as SpanType))
  else if (dimension === 'year') sorted.sort((a, b) => Number(a.key) - Number(b.key))
  else sorted.sort((a, b) => a.label.localeCompare(b.label))
  return [...sorted, ...missing]
}

/** The order a distribution is shown in by default: statuses and years by value, the others by count. */
export function defaultOrder (dimension: Dimension): RowOrder {
  return dimension === 'type' || dimension === 'year' ? 'value' : 'count'
}
