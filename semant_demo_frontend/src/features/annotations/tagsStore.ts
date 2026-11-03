import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { Tag, PostTag, PatchTag } from 'src/generated/api'
import { useTagsRepository } from './useTagsRepository'
import { ongoingNotification, warningNotification } from 'src/shared/notification'
import { incompleteWriteMessage, incompleteWriteStep } from 'src/shared/writeOutcome'
import { captureSession, createContextGuard, createScope } from 'src/shared/api'

/** Outcome of a bulk deletion. `deleted`: the tags the backend deleted, among them
 * `attributesKept`: deleted, but their ids could not be removed from the attributes that list
 * them (#508). `failed`: not deleted, or not known to be. */
export interface DeleteManyResult {
  deleted: string[]
  attributesKept: string[]
  failed: string[]
}

/** How deleting one tag ended. */
export type TagDeletion = 'deleted' | 'attributesKept' | 'failed'

/** The last step of a tag deletion (#508): when only it fails, the tag is deleted and its id
 * stays on the attributes that list it, shown there as a deleted tag. Deleting the tag again
 * cannot repair that: the tag is gone. */
const ATTRIBUTE_CLEANUP_STEP = 'remove_from_attributes'

const tagDeletedAnyway = async (err: unknown) => await incompleteWriteStep(err) === ATTRIBUTE_CLEANUP_STEP

const attributesKeptMessage = (names: string[]) =>
  `${names.length === 1 ? `Tag ${names[0]} was` : `Tags ${names.join(', ')} were`} deleted, but ` +
  `the attributes that applied to ${names.length === 1 ? 'it still list it' : 'them still list them'} ` +
  'as a deleted tag. Remove it there when you edit the attribute.'

/**
 * Tag definitions of one collection. Loading another collection's tags first drops the
 * current ones, and an answer for an earlier collection (or an earlier reload) is ignored.
 * Nothing started before a sign-out changes the store afterwards (`captureSession`).
 */
export const useTagsStore = defineStore('tags', () => {
  const tagsRepository = useTagsRepository()
  const scope = createScope()
  const listRequests = createContextGuard()
  const tagRequests = createContextGuard()
  const tags = ref<Tag[]>([])
  const activeTag = ref<Tag | null>(null)
  const error = ref<string | null>(null)
  const loading = ref<boolean>(false)
  const pendingDeleteIds = ref<Set<string>>(new Set())
  // Deletions the backend acknowledged in this scope. Tag ids are never reused, so a list
  // answer that predates a deletion cannot bring the tag back.
  const deletedIds = new Set<string>()

  const visibleTags = computed(() =>
    tags.value.filter((tag) => !pendingDeleteIds.value.has(tag.id))
  )

  const forgetDeleted = (ids: string[]) => {
    ids.forEach((id) => deletedIds.add(id))
    tags.value = tags.value.filter((tag) => !deletedIds.has(tag.id))
    if (activeTag.value && deletedIds.has(activeTag.value.id)) activeTag.value = null
  }

  const fetchTagsByCollection = async (collectionId: string) => {
    if (scope.enter(collectionId)) {
      tags.value = []
      activeTag.value = null
      deletedIds.clear()
    }
    listRequests.enter()
    const isCurrent = listRequests.capture()
    loading.value = true
    error.value = null
    try {
      const data = await tagsRepository.getAllByCollection(collectionId)
      if (isCurrent()) tags.value = data.filter((tag) => !deletedIds.has(tag.id))
    } catch (err) {
      if (!isCurrent()) return
      error.value = 'Failed to fetch tags'
      console.error('Error fetching tags:', err)
    } finally {
      if (isCurrent()) loading.value = false
    }
  }

  /** Drops all tags (logout). */
  const clear = () => {
    scope.reset()
    listRequests.enter()
    tagRequests.enter()
    deletedIds.clear()
    tags.value = []
    activeTag.value = null
    error.value = null
    loading.value = false
  }

  const fetchTag = async (tagUuid: string) => {
    tagRequests.enter()
    const isCurrent = tagRequests.capture()
    const inSession = captureSession()
    const applies = () => isCurrent() && inSession()
    if (activeTag.value?.id !== tagUuid) activeTag.value = null
    loading.value = true
    error.value = null
    try {
      const data = await tagsRepository.getById(tagUuid)
      if (applies()) activeTag.value = data
    } catch (err) {
      if (!applies()) return
      error.value = 'Failed to fetch tag'
      console.error('Error fetching tag:', err)
    } finally {
      if (applies()) loading.value = false
    }
  }

  const createTag = async (collectionId: string, payload: PostTag) => {
    const notif = ongoingNotification('Creating tag...')
    const inScope = scope.capture()
    const inSession = captureSession()
    loading.value = true
    error.value = null
    try {
      const createdTag = await tagsRepository.create(collectionId, payload)
      if (!inSession()) {
        notif.dismiss()
        return createdTag
      }
      if (inScope() && scope.key === collectionId) tags.value.push(createdTag)
      notif.success('Tag created')
      return createdTag
    } catch (err) {
      if (!inSession()) {
        notif.dismiss()
        throw err
      }
      error.value = 'Failed to create tag'
      console.error('Error creating tag:', err)
      notif.error(await incompleteWriteMessage(err, 'Failed to create tag'))
      throw err
    } finally {
      if (inSession()) loading.value = false
    }
  }

  /** Deletes one tag and reports the outcome; resolves to it: `attributesKept` when the tag was
   * deleted but its id could not be removed from the attributes that list it (#508). */
  const deleteTag = async (tagUuid: string): Promise<TagDeletion> => {
    const notif = ongoingNotification('Deleting tag...')
    const inScope = scope.capture()
    const inSession = captureSession()
    loading.value = true
    error.value = null
    try {
      await tagsRepository.delete(tagUuid)
      if (!inSession()) {
        notif.dismiss()
        return 'deleted'
      }
      if (inScope()) forgetDeleted([tagUuid])
      notif.success('Tag deleted')
      return 'deleted'
    } catch (err) {
      if (!inSession()) {
        notif.dismiss()
        return 'failed'
      }
      if (await tagDeletedAnyway(err)) {
        console.error('Error removing the deleted tag from attributes:', err)
        const name = tags.value.find((tag) => tag.id === tagUuid)?.name ?? tagUuid
        if (inScope()) forgetDeleted([tagUuid])
        notif.dismiss()
        warningNotification(attributesKeptMessage([name]))
        return 'attributesKept'
      }
      error.value = 'Failed to delete tag'
      console.error('Error deleting tag:', err)
      notif.error(await incompleteWriteMessage(err, 'Failed to delete tag'))
      return 'failed'
    } finally {
      if (inSession()) loading.value = false
    }
  }

  /**
   * Deletes the tags one by one (best effort). The selected tags are hidden while their
   * deletions run; afterwards only the deletions the backend reports are applied, failed tags
   * stay visible, and both those and the deleted tags whose ids stayed on attributes (#508) are
   * reported by name. Resolves when every deletion has finished.
   */
  const deleteManyTags = async (tagUuids: string[]): Promise<DeleteManyResult> => {
    if (tagUuids.length === 0) return { deleted: [], attributesKept: [], failed: [] }
    const notif = ongoingNotification(`Deleting ${tagUuids.length} tags...`)
    const inScope = scope.capture()
    const inSession = captureSession()
    const nameOf = new Map(tags.value.map((tag) => [tag.id, tag.name]))
    const names = (ids: string[]) => ids.map((id) => nameOf.get(id) ?? id)
    tagUuids.forEach((id) => pendingDeleteIds.value.add(id))
    error.value = null
    try {
      const results = await Promise.allSettled(tagUuids.map((id) => tagsRepository.delete(id)))
      const keptOnAttributes = await Promise.all(
        results.map((r) => r.status === 'rejected' ? tagDeletedAnyway(r.reason) : Promise.resolve(false)))
      const deleted = tagUuids.filter((_, i) => results[i].status === 'fulfilled' || keptOnAttributes[i])
      const attributesKept = tagUuids.filter((_, i) => keptOnAttributes[i])
      const failed = tagUuids.filter((id) => !deleted.includes(id))
      if (!inSession()) {
        notif.dismiss()
        return { deleted, attributesKept, failed }
      }
      if (inScope()) forgetDeleted(deleted)
      if (!failed.length && !attributesKept.length) {
        notif.success(`${deleted.length} tag${deleted.length === 1 ? '' : 's'} deleted`)
      } else if (!failed.length) {
        console.error('Error removing deleted tags from attributes:', results)
        notif.dismiss()
        warningNotification(attributesKeptMessage(names(attributesKept)))
      } else {
        const failures = failed.map((id) => results[tagUuids.indexOf(id)]).flatMap((r) => (r.status === 'rejected' ? [r.reason] : []))
        error.value = 'Failed to delete some tags'
        console.error('Error deleting tags:', failures)
        // The backend's message for the first failure, when it says where a deletion stopped.
        const detail = await incompleteWriteMessage(failures[0], '')
        const message = [
          `Deleted ${deleted.length} of ${tagUuids.length} tags; not deleted: ${names(failed).join(', ')}.`,
          detail,
          attributesKept.length ? attributesKeptMessage(names(attributesKept)) : ''
        ]
        notif.error(message.filter(Boolean).join(' '))
      }
      return { deleted, attributesKept, failed }
    } finally {
      tagUuids.forEach((id) => pendingDeleteIds.value.delete(id))
    }
  }

  const updateTag = async (tagUuid: string, payload: PatchTag) => {
    const notif = ongoingNotification('Updating tag...')
    const inScope = scope.capture()
    const inSession = captureSession()
    loading.value = true
    error.value = null
    try {
      const updatedTag = await tagsRepository.update(tagUuid, payload)
      if (!inSession()) {
        notif.dismiss()
        return updatedTag
      }
      if (inScope()) {
        const existingIndex = tags.value.findIndex((tag) => tag.id === updatedTag.id)
        if (existingIndex >= 0) {
          tags.value[existingIndex] = updatedTag
        }
        if (activeTag.value?.id === updatedTag.id) activeTag.value = updatedTag
      }
      notif.success('Tag updated')
      return updatedTag
    } catch (err) {
      if (!inSession()) {
        notif.dismiss()
        throw err
      }
      error.value = 'Failed to update tag'
      console.error('Error updating tag:', err)
      notif.error('Failed to update tag')
      throw err
    } finally {
      if (inSession()) loading.value = false
    }
  }

  return {
    tags: visibleTags,
    error,
    loading,
    activeTag,
    deleteTag,
    deleteManyTags,
    updateTag,
    fetchTagsByCollection,
    clear,
    createTag,
    fetchTag
  }
})
