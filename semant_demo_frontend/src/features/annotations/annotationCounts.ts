import { AnnotationSort, SpanType } from 'src/generated/api'
import { useApi } from 'src/shared/api'

export interface AnnotationCounts {
  /** Approved annotations. */
  approved: number
  /** AI suggestions not yet approved or rejected. */
  suggestions: number
  /** Rejected suggestions (the review's negative feedback). */
  rejected: number
}

/** Reads the counts of what an action would affect. */
export type AnnotationCounter = () => Promise<AnnotationCounts>

/**
 * How many annotations a collection holds, of the given tags only when `tagIds` is set
 * (the concordance query's totals; one row is read per type, sorted by text, which counts
 * without reading the documents).
 */
export async function countAnnotations (collectionId: string, tagIds?: string[]): Promise<AnnotationCounts> {
  const api = useApi().default
  const total = async (type: SpanType) => (await api.listCollectionAnnotationsApiUserCollectionsCollectionIdAnnotationsGet({
    collectionId, tagId: tagIds, type: [type], sort: AnnotationSort.text, limit: 1
  })).total
  const [approved, suggestions, rejected] = await Promise.all([total(SpanType.pos), total(SpanType.auto), total(SpanType.neg)])
  return { approved, suggestions, rejected }
}

/** The counts of several collections added up. */
export async function countAnnotationsInCollections (collectionIds: string[]): Promise<AnnotationCounts> {
  const all = await Promise.all(collectionIds.map((id) => countAnnotations(id)))
  return all.reduce((sum, c) => ({
    approved: sum.approved + c.approved,
    suggestions: sum.suggestions + c.suggestions,
    rejected: sum.rejected + c.rejected
  }), { approved: 0, suggestions: 0, rejected: 0 })
}
