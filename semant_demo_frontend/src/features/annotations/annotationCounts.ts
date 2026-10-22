import { SpanType } from 'src/generated/api'
import { useApi } from 'src/shared/api'

export interface AnnotationCounts {
  /** Approved annotations. */
  approved: number
  /** AI suggestions not yet approved or rejected. */
  suggestions: number
}

/** Reads the counts of what an action would affect. */
export type AnnotationCounter = () => Promise<AnnotationCounts>

/**
 * How many annotations a collection holds, of the given tags only when `tagIds` is set
 * (the concordance query's totals; one row is read per type).
 */
export async function countAnnotations (collectionId: string, tagIds?: string[]): Promise<AnnotationCounts> {
  const api = useApi().default
  const total = async (type: SpanType) => (await api.listCollectionAnnotationsApiUserCollectionsCollectionIdAnnotationsGet({
    collectionId, tagId: tagIds, type: [type], limit: 1
  })).total
  const [approved, suggestions] = await Promise.all([total(SpanType.pos), total(SpanType.auto)])
  return { approved, suggestions }
}

/** The counts of several collections added up. */
export async function countAnnotationsInCollections (collectionIds: string[]): Promise<AnnotationCounts> {
  const all = await Promise.all(collectionIds.map((id) => countAnnotations(id)))
  return all.reduce((sum, c) => ({ approved: sum.approved + c.approved, suggestions: sum.suggestions + c.suggestions }),
    { approved: 0, suggestions: 0 })
}
