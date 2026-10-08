import type { Collection } from 'src/generated/api'

/**
 * What the signed-in user may do with a collection they can read, mirroring the backend
 * rules (ADR 0007, `features/collections/access.py`). The backend enforces them; the UI
 * uses this only to hide or disable controls that would be refused.
 */
export interface CollectionRights {
  /** Create/edit/delete annotations and run AI suggestions (owner and shared users). */
  annotate: boolean
  /** Create/edit/delete tag definitions (owner and shared users). */
  editTags: boolean
  /** See who the collection is shared with (owner and shared users). */
  viewMembers: boolean
  /** Add/remove documents and chunks (owner only). */
  editMembership: boolean
  /** Edit name, description, color; delete the collection (owner only). */
  editMetadata: boolean
  /** Share/unshare (owner only). */
  share: boolean
}

const NONE: CollectionRights = {
  annotate: false, editTags: false, viewMembers: false, editMembership: false, editMetadata: false, share: false
}

/**
 * Rights for a collection as returned by the API (`isSharedWithMe` is set for the
 * signed-in user). A collection that is not loaded yet grants nothing, so owner controls
 * do not flash up for shared users.
 */
export function collectionRights (collection: Pick<Collection, 'isSharedWithMe'> | null | undefined): CollectionRights {
  if (!collection) return NONE
  const owner = !collection.isSharedWithMe
  return {
    annotate: true,
    editTags: true,
    viewMembers: true,
    editMembership: owner,
    editMetadata: owner,
    share: owner
  }
}
