import { Cardinality, SpanType, type AnnotatedDocument, type AnnotationFacets, type AnnotationFacetsRequest, type Attribute, type Facet, type Tag } from 'src/generated/api'
import { orderedValues, valueName } from 'src/features/attributes/attributeForm'
import { languageLabel, libraryLabel } from 'src/features/analytics/corpusOverview'
import { MAX_FACET_ATTRIBUTES, annotationFilters, ranking, type ConcordanceFilters } from '../concordance/concordanceStore'

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

/** The facet request of the statistics of `f`: the query itself, every facet over its own population,
 * and the accepted values of each of `attributeIds` (#819). */
export function statisticsRequest (f: ConcordanceFilters, attributeIds: string[] = []): AnnotationFacetsRequest {
  return {
    ...annotationFilters(f),
    ranking: ranking(f),
    facets: [...DIMENSIONS, ...attributeIds.slice(0, MAX_FACET_ATTRIBUTES).map(attributeFacetName)],
    selfExclusion: false
  }
}

export const attributeFacetName = (attributeId: string) => `attribute:${attributeId}`

/** One row of a distribution: a value, or the annotations without one (`missing`). */
export interface DistributionRow {
  key: string
  label: string
  count: number
  /** `count` of the distribution's total (0..1); 0 when the total is 0; null when no meaningful denominator
   * exists (retained values joined the counts of an applicable-only population, #819). */
  share: number | null
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

/** The numbers of the statistics' summary line: total, distinct documents (null: not counted) and the
 * denominator of every share. */
export function summaryOf (statistics: AnnotationFacets) {
  const total = statistics.facets[0]?.total ?? 0
  return {
    total,
    documents: facetOf(statistics, 'document')?.distinct ?? null,
    topK: isTopK(statistics),
    k: statistics.k ?? null,
    denominator: denominatorText(statistics, total)
  }
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

// ── Accepted attribute values (#819) ──

/** The counting contract of the accepted-value distributions (#334): the population is the confirmed
 * annotations of the query whose current tag the attribute applies to; a value counts the annotations
 * of it holding the value; values kept after a retag (#500) are no current classification and count
 * only when asked for, as a population of their own. */
export interface AttributeDistribution {
  attribute: Attribute
  rows: DistributionRow[]
  /** Confirmed annotations of the query the attribute applies to: the denominator of every share. */
  eligible: number
  /** Of them, annotations with at least one value (one with several counts once). */
  withValue: number
  /** Values assigned to them, one per annotation and value: more than `withValue` for a multi-valued attribute. */
  assignments: number
  /** Stored holders of values, retained ones included: what the rows count when `includeRetained` asks. */
  stored: number
  /** Annotations of the query with no value of the attribute (the Missing row). */
  missing: number
  /** Values retained on annotations whose tag the attribute no longer applies to (never in the counts above). */
  retained: number
  multiValued: boolean
}

/** The tags a drill-down of the attribute lists: those it applies to within the query's own tag
 * filter ([]: any tag, as the query); null when none, so no annotation is counted. */
export function applicableTags (attribute: Attribute, f: ConcordanceFilters): string[] | null {
  if (attribute.allTags) return f.tagIds
  const own = attribute.tagIds ?? []
  const tags = f.tagIds.length ? own.filter(t => f.tagIds.includes(t)) : own
  return tags.length ? tags : null
}

/**
 * The filter change that lists exactly the annotations a value row counts: confirmed, holding the
 * value, of a tag the attribute applies to (`stored`: any tag, the stored-value filter of #500, a
 * different population), or, with `valueId` null, confirmed annotations without any value. Null
 * when the query cannot be narrowed that way: the attribute's own filter in the query excludes the value
 * (values of one attribute match any, so the query AND the value is not one filter).
 */
export function attributeDrillChange (attribute: Attribute, valueId: string | null, f: ConcordanceFilters,
  stored = false): Partial<ConcordanceFilters> | null {
  const prefix = `${attribute.id}:`
  const own = f.attributeValues.filter(v => v.startsWith(prefix))
  const others = f.attributeValues.filter(v => !v.startsWith(prefix))
  if (valueId && own.length && !own.includes(`${prefix}${valueId}`)) return null
  if (valueId && f.attributeUnassigned.includes(attribute.id)) return null
  if (!valueId && own.length) return null
  const tags = stored ? f.tagIds : applicableTags(attribute, f)
  if (!tags) return null
  const unassigned = f.attributeUnassigned.filter(a => a !== attribute.id)
  return {
    types: [SpanType.pos],
    tagIds: tags,
    attributeValues: valueId ? [...others, `${prefix}${valueId}`] : others,
    attributeUnassigned: valueId ? unassigned : [...unassigned, attribute.id]
  }
}

/** The distribution of one attribute from its facet, or null when the server gave no statistics for it. */
export function attributeDistribution (facet: Facet | null, attribute: Attribute, f: ConcordanceFilters,
  drillable: boolean, includeRetained: boolean): AttributeDistribution | null {
  if (!facet || facet.eligible == null || facet.withValue == null || facet.assignments == null) return null
  const eligible = facet.eligible
  // Retained values come from outside the eligible population: no share of it is meaningful then.
  const share = (n: number) => (includeRetained ? null : eligible ? n / eligible : 0)
  const counted = new Map(facet.values.map(v => [v.value, v]))
  const defined = orderedValues(attribute).filter(v => !v.retired || (counted.get(v.id)?.count ?? 0) > 0)
  const rows: DistributionRow[] = defined.map(value => {
    const c = counted.get(value.id)
    const count = includeRetained ? c?.count ?? 0 : (c?.count ?? 0) - (c?.inapplicable ?? 0)
    return {
      key: value.id,
      label: valueName(value),
      count,
      share: share(count),
      kind: 'value',
      drill: drillable ? attributeDrillChange(attribute, value.id, f, includeRetained) : null
    }
  })
  const missing = Math.max(0, eligible - facet.withValue)
  if (missing > 0 && !includeRetained) {
    rows.push({
      key: '__missing__',
      label: 'Not assigned',
      count: missing,
      share: share(missing),
      kind: 'missing',
      drill: drillable ? attributeDrillChange(attribute, null, f) : null
    })
  }
  return {
    attribute,
    rows,
    eligible,
    withValue: facet.withValue,
    assignments: facet.assignments,
    stored: facet.values.reduce((n, v) => n + v.count, 0),
    missing: Math.max(0, eligible - facet.withValue),
    retained: facet.values.reduce((n, v) => n + (v.inapplicable ?? 0), 0),
    multiValued: attribute.cardinality === Cardinality.multi
  }
}
