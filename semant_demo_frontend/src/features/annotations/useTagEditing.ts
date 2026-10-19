import type { PatchTag, PostTag, Tag } from 'src/generated/api'
import { useTagsStore } from './tagsStore'
import useTagsDialog from './useTagsDialog'

/**
 * Creates and edits the tags of a collection through the tag dialog; reloads the tag list after each change.
 * A failed create or update is reported by the tags store, so it ends here instead of as an unhandled rejection.
 */
export function useTagEditing (collectionId: () => string) {
  const tagsStore = useTagsStore()
  const { openTagsDialog } = useTagsDialog()

  const createTag = (onCreated?: (tag: Tag) => Promise<void> | void) => {
    openTagsDialog({ dialogType: 'CREATE' }).onOk(async (tagData: PostTag) => {
      let tag: Tag
      try {
        tag = await tagsStore.createTag(collectionId(), tagData)
      } catch {
        return
      }
      await tagsStore.fetchTagsByCollection(collectionId())
      await onCreated?.(tag)
    })
  }

  const editTag = (tag: Tag) => {
    openTagsDialog({ dialogType: 'EDIT', tag }).onOk(async (updatedData: PatchTag) => {
      await updateTag(tag, updatedData)
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
