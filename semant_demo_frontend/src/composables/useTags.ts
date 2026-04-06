import { computed } from 'vue'

import { useTagsStore } from 'src/stores/tagsStore'
import { TagCreate } from 'src/models/tags'

const useTags = () => {
  const tagsStore = useTagsStore()

  const loadTags = (collectionId: string) => tagsStore.fetchTags(collectionId)
  const createTag = (collectionId: string, payload: TagCreate) => tagsStore.createTag(collectionId, payload)

  const tags = computed(() => tagsStore.tags)
  const loading = computed(() => tagsStore.loading)
  const error = computed(() => tagsStore.error)

  return {
    loadTags,
    createTag,
    tags,
    loading,
    error
  }
}

export default useTags
