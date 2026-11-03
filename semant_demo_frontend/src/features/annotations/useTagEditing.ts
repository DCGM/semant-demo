import type { PatchTag, PostTag, Tag } from 'src/generated/api'
import { useTagsStore } from './tagsStore'
import useTagsDialog from './useTagsDialog'

/**
 * Creates and edits the tags of a collection through the tag dialog, which saves the tag and the
 * attributes that apply to it itself (#516); reloads the tag list after each change. A failed
 * create or update is reported by the tags store and shown by the dialog, which stays open.
 * `onCreated` runs only when the dialog saved everything: closing it after an attribute change
 * failed keeps (and lists) a created tag but goes no further, so no text is tagged with it.
 */
export function useTagEditing (collectionId: () => string) {
  const tagsStore = useTagsStore()
  const { openTagsDialog } = useTagsDialog()

  const open = (tag: Tag | undefined, onSaved?: (tag: Tag) => Promise<void> | void) => {
    let saved = false
    const save = async (payload: PostTag, existing: Tag | null) => {
      const result = await (existing
        ? tagsStore.updateTag(existing.id, payload)
        : tagsStore.createTag(collectionId(), payload))
      saved = true
      return result
    }
    openTagsDialog({ tag, collectionId: collectionId(), save })
      .onOk(async (result: Tag) => {
        await tagsStore.fetchTagsByCollection(collectionId())
        await onSaved?.(result)
      })
      .onCancel(async () => {
        if (saved) await tagsStore.fetchTagsByCollection(collectionId())
      })
  }

  const createTag = (onCreated?: (tag: Tag) => Promise<void> | void) => open(undefined, onCreated)

  const editTag = (tag: Tag) => open(tag)

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
