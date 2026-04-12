import { computed } from 'vue'

import { useTagsStore } from 'src/stores/tagsStore'
import { PostTag } from 'src/models/tags'
import { PatchTag } from 'src/generated/api'

const useTags = () => {
  const tagsStore = useTagsStore()

  const loadTagsByCollection = (collectionId: string) => tagsStore.fetchTagsByCollection(collectionId)
  const loadTag = (tagUuid: string) => tagsStore.fetchTag(tagUuid)
  const createTag = (collectionId: string, payload: PostTag) => tagsStore.createTag(collectionId, payload)
  const deleteTag = (tagUuid: string) => tagsStore.deleteTag(tagUuid)
  const updateTag = (tagUuid: string, payload: PatchTag) => tagsStore.updateTag(tagUuid, payload)

  const tags = computed(() => tagsStore.tags)
  const loading = computed(() => tagsStore.loading)
  const error = computed(() => tagsStore.error)
  const activeTag = computed(() => tagsStore.activeTag)

  return {
    loadTagsByCollection,
    loadTag,
    createTag,
    deleteTag,
    updateTag,
    tags,
    loading,
    error,
    activeTag
  }
}

export default useTags
