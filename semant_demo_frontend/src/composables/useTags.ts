import { computed } from 'vue'

import { useTagsStore } from 'src/stores/tagsStore'
import { PostTag } from 'src/models/tags'
import { PatchTag } from 'src/generated/api'

const useTags = () => {
  const tagsStore = useTagsStore()

  const loadTags = (collectionId: string) => tagsStore.fetchTags(collectionId)
  const createTag = (collectionId: string, payload: PostTag) => tagsStore.createTag(collectionId, payload)
  const deleteTag = (collectionId: string, tagUuid: string) => tagsStore.deleteTag(collectionId, tagUuid)
  const updateTag = (collectionId: string, tagUuid: string, payload: PatchTag) => tagsStore.updateTag(collectionId, tagUuid, payload)

  const tags = computed(() => tagsStore.tags)
  const loading = computed(() => tagsStore.loading)
  const error = computed(() => tagsStore.error)

  return {
    loadTags,
    createTag,
    deleteTag,
    updateTag,
    tags,
    loading,
    error
  }
}

export default useTags
