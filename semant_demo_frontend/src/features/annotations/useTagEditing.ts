import type { PatchTag, PostTag, Tag } from 'src/generated/api'
import { useTagsStore } from './tagsStore'
import useTagsDialog from './useTagsDialog'

/**
 * Creates and edits the tags of a collection through the tag dialog, which saves the tag and the
 * attributes that apply to it itself (#516); reloads the tag list after each change. A failed
 * create or update is reported by the tags store and shown by the dialog, which stays open.
 */
export function useTagEditing (collectionId: () => string) {
  const tagsStore = useTagsStore()
  const { openTagsDialog } = useTagsDialog()

  const save = (payload: PostTag, existing: Tag | null) =>
    existing ? tagsStore.updateTag(existing.id, payload) : tagsStore.createTag(collectionId(), payload)

  const createTag = (onCreated?: (tag: Tag) => Promise<void> | void) => {
    openTagsDialog({ collectionId: collectionId(), save }).onOk(async (tag: Tag) => {
      await tagsStore.fetchTagsByCollection(collectionId())
      await onCreated?.(tag)
    })
  }

  const editTag = (tag: Tag) => {
    openTagsDialog({ tag, collectionId: collectionId(), save }).onOk(async () => {
      await tagsStore.fetchTagsByCollection(collectionId())
    })
  }

  const updateExamples = async (tag: Tag, examples: string[]) => {
    await updateTag(tag, { examples })
  }

  const updateTag = async (tag: Tag, update: PatchTag) => {
    try {
      await tagsStore.updateTag(tag.id, update)
    } catch {
      return
    }
    await tagsStore.fetchTagsByCollection(collectionId())
  }

  return { createTag, editTag, updateExamples }
}
