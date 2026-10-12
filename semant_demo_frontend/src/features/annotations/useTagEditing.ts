import type { PatchTag, PostTag, Tag } from 'src/generated/api'
import { useTagsStore } from './tagsStore'
import useTagsDialog from './useTagsDialog'

/** Creates and edits the tags of a collection through the tag dialog; reloads the tag list after each change. */
export function useTagEditing (collectionId: () => string) {
  const tagsStore = useTagsStore()
  const { openTagsDialog } = useTagsDialog()

  const createTag = (onCreated?: (tag: Tag) => Promise<void> | void) => {
    openTagsDialog({ dialogType: 'CREATE' }).onOk(async (tagData: PostTag) => {
      const tag = await tagsStore.createTag(collectionId(), tagData)
      await tagsStore.fetchTagsByCollection(collectionId())
      await onCreated?.(tag)
    })
  }

  const editTag = (tag: Tag) => {
    openTagsDialog({ dialogType: 'EDIT', tag }).onOk(async (updatedData: PatchTag) => {
      await tagsStore.updateTag(tag.id, updatedData)
      await tagsStore.fetchTagsByCollection(collectionId())
    })
  }

  const updateExamples = async (tag: Tag, examples: string[]) => {
    await tagsStore.updateTag(tag.id, { examples })
    await tagsStore.fetchTagsByCollection(collectionId())
  }

  return { createTag, editTag, updateExamples }
}
