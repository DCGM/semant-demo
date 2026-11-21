import { AnnotationSort, SpanType, TextScope, type Attribute, type LiveQuery, type Tag } from 'src/generated/api'
import { annotationFilters, defaultFilters, normalizeDocumentFilters, withMode, type ConcordanceFilters } from './concordanceStore'

/** What a live filter keeps of the workspace (#824): the annotation query, its order and the shown
 * attribute columns. A Find similar source names one annotation and is not kept; a similarity text is. */
export function liveQueryOf (f: ConcordanceFilters, shownAttributeIds: string[]): LiveQuery {
  const attributeSort = f.sort === AnnotationSort.attribute && f.sortAttribute
  return {
    filters: annotationFilters(f),
    sort: attributeSort || f.sort !== AnnotationSort.attribute ? f.sort : AnnotationSort.document,
    sortAttribute: attributeSort ? f.sortAttribute : null,
    descending: f.descending,
    shownAttributeIds: [...shownAttributeIds]
  }
}

/** The workspace filters of a saved live filter: every filter it does not name is the default, and
 * the retrieval mode follows from them as in the workspace (a similarity text ranks: hybrid). */
export function filtersOf (q: LiveQuery): ConcordanceFilters {
  const f = q.filters ?? {}
  return withMode({
    ...defaultFilters(),
    tagIds: [...(f.tagIds ?? [])],
    types: f.types?.length ? [...f.types] : [SpanType.pos, SpanType.auto],
    text: f.q ?? '',
    similarity: f.rankingQuery ?? '',
    textScope: f.textScope ?? TextScope.annotation,
    documentIds: [...(f.documentIds ?? [])],
    documentFilters: normalizeDocumentFilters(f.documentFilters ?? {}),
    attributeValues: [...(f.attributeValues ?? [])],
    attributeUnassigned: [...(f.attributeUnassigned ?? [])],
    near: f.near ?? null,
    sort: q.sort ?? AnnotationSort.document,
    sortAttribute: q.sort === AnnotationSort.attribute ? q.sortAttribute ?? null : null,
    descending: q.descending ?? false
  })
}

/** `value` with empty fields dropped and lists sorted: every list of a live query is a set. */
function canonical (value: unknown): unknown {
  if (Array.isArray(value)) {
    const items = value.map(canonical)
    return items.every(i => typeof i !== 'object') ? [...items].sort() : items
  }
  if (value && typeof value === 'object') {
    const entries = Object.entries(value)
      .map(([k, v]) => [k, canonical(v)] as const)
      .filter(([, v]) => v !== null && v !== undefined && !(Array.isArray(v) && !v.length) &&
        !(typeof v === 'object' && !Array.isArray(v) && !Object.keys(v as object).length))
      .sort(([a], [b]) => a.localeCompare(b))
    return Object.fromEntries(entries)
  }
  return value
}

/** Whether the workspace shows exactly the saved live filter `q` (its query, order and columns). */
export function sameQuery (current: LiveQuery, q: LiveQuery): boolean {
  const saved = liveQueryOf(filtersOf(q), q.shownAttributeIds ?? [])
  return JSON.stringify(canonical(current)) === JSON.stringify(canonical(saved))
}

/** What the live filter names that the collection no longer has (#824): such parts match nothing. */
export interface MissingReferences {
  tags: number
  attributes: number
  values: number
}

export function missingReferences (q: LiveQuery, tags: Tag[], attributes: Attribute[]): MissingReferences {
  const f = q.filters ?? {}
  const tagIds = new Set(tags.map(t => t.id))
  const byId = new Map(attributes.map(a => [a.id, a]))
  const named = new Set([...(f.tagIds ?? []), ...(f.near?.tagIds ?? [])])
  const values = [...(f.attributeValues ?? []), ...(f.near?.attributeValues ?? [])].map(v => v.split(':', 2) as [string, string])
  const attributeIds = new Set([...values.map(([a]) => a), ...(f.attributeUnassigned ?? []),
    ...(q.sortAttribute ? [q.sortAttribute] : []), ...(q.shownAttributeIds ?? [])])
  return {
    tags: [...named].filter(id => !tagIds.has(id)).length,
    attributes: [...attributeIds].filter(id => !byId.has(id)).length,
    values: new Set(values.filter(([a, v]) => byId.has(a) && !(byId.get(a)?.values ?? []).some(x => x.id === v))
      .map(([a, v]) => `${a}:${v}`)).size
  }
}

/** The warning of a live filter whose tags or attributes were deleted; null when none were. */
export function missingText (m: MissingReferences): string | null {
  const parts = [
    m.tags && `${m.tags} deleted tag${m.tags === 1 ? '' : 's'}`,
    m.attributes && `${m.attributes} deleted attribute${m.attributes === 1 ? '' : 's'}`,
    m.values && `${m.values} deleted attribute value${m.values === 1 ? '' : 's'}`
  ].filter(Boolean)
  if (!parts.length) return null
  return `This live filter refers to ${parts.join(', ')}, which no annotation can match. Update it to save the current filters.`
}
