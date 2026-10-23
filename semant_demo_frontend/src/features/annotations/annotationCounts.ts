import type { AnnotationCounts } from 'src/generated/api'
import { useApi } from 'src/shared/api'
import { plural } from 'src/shared/plural'

/** How many annotations a collection holds per type, of the given tags only when `tagIds` is set. */
export async function countAnnotations (collectionId: string, tagIds?: string[]): Promise<AnnotationCounts> {
  return await useApi().default.countCollectionAnnotationsApiUserCollectionsCollectionIdAnnotationsCountsGet({
    collectionId, tagId: tagIds
  })
}

/** The annotations as text ("1 approved annotation and 2 rejected suggestions"); empty when there are none. */
export function describeAnnotations ({ approved, suggestions, rejected }: AnnotationCounts): string {
  const parts = []
  if (approved) parts.push(plural(approved, 'approved annotation'))
  if (suggestions) parts.push(plural(suggestions, 'unresolved AI suggestion'))
  if (rejected) parts.push(plural(rejected, 'rejected suggestion'))
  return parts.length > 1 ? `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}` : parts.join('')
}

/** What deleting these tags would delete along, for the delete confirmation. */
export const annotationsOfTags = (collectionId: string, tagIds: string[]) => async () =>
  describeAnnotations(await countAnnotations(collectionId, tagIds))

/** What deleting these collections would delete along (their counts added up). */
export const annotationsOfCollections = (collectionIds: string[]) => async () => {
  const all = await Promise.all(collectionIds.map((id) => countAnnotations(id)))
  return describeAnnotations(all.reduce((sum, c) => ({
    approved: sum.approved + c.approved,
    suggestions: sum.suggestions + c.suggestions,
    rejected: sum.rejected + c.rejected
  }), { approved: 0, suggestions: 0, rejected: 0 }))
}
