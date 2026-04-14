import { useApi } from 'src/composables/useApi'
import { TagSpan } from 'src/generated/api/models/TagSpan'
import { ref } from 'vue'

export function useTagging() {
  const api = useApi().default
  const collectionChunks = ref<
    Awaited<
      ReturnType<typeof api.getCollectionChunksApiUserCollectionChunksGet>
    >['chunksOfCollection']
  >([])
  const tagSpans = ref<TagSpan[]>([])
  const isProcessing = ref(false)
  const availableTags = ref<
    Awaited<ReturnType<typeof api.getTagsApiTagsGet>>['tagsLst']
  >([])

  const getCollectionChunksPaged = async (
    collectionId: Parameters<
      typeof api.getCollectionChunksApiUserCollectionChunksGet
    >[0]['collectionId']
  ) => {
    isProcessing.value = true
    try {
      const response = await api.getCollectionChunksApiUserCollectionChunksGet({
        collectionId
      })
      collectionChunks.value = response.chunksOfCollection
      collectionChunks.value = response.chunksOfCollection
      return response.chunksOfCollection
    } catch (error) {
      console.error('Error fetching collection chunks:', error)
      return []
    } finally {
      isProcessing.value = false
    }
  }

  const fetchTagSpansForChunk = async (
    chunkId: Parameters<
      typeof api.readTagSpansApiTagSpansChunkIdGet
    >[0]['chunkId']
  ): Promise<TagSpan[]> => {
    try {
      const response = await api.readTagSpansApiTagSpansChunkIdGet({
        chunkId
      })
      return response
    } catch (error) {
      console.error('Error fetching tag spans:', error)
      return []
    }
  }

  const fetchTagSpansMapForChunks = async (chunkIds: string[]) => {
    const pairs = await Promise.all(
      chunkIds.map(async (chunkId) => {
        const spans = await fetchTagSpansForChunk(chunkId)
        return [chunkId, spans] as const
      })
    )

    return pairs.reduce<Record<string, TagSpan[]>>((acc, [chunkId, spans]) => {
      acc[chunkId] = spans
      return acc
    }, {})
  }

  const getTagSpans = async (
    chunkId: Parameters<
      typeof api.readTagSpansApiTagSpansChunkIdGet
    >[0]['chunkId']
  ): Promise<TagSpan[]> => {
    isProcessing.value = true
    try {
      const response = await fetchTagSpansForChunk(chunkId)
      tagSpans.value = response
      console.log('Fetched tag spans:', response)
      return response
    } catch (error) {
      console.error('Error fetching tag spans:', error)
      return []
    } finally {
      isProcessing.value = false
    }
  }

  const createTagSpan = async (
    data: Parameters<
      typeof api.upsertTagSpansApiTagSpansPost
    >[0]['tagSpanCreateSeparateRequest']
  ) => {
    isProcessing.value = true
    try {
      const response = await api.upsertTagSpansApiTagSpansPost({
        tagSpanCreateSeparateRequest: {
          span: data.span
        }
      })
      console.log('Tag span(s) created successfully:', response)
    } catch (error) {
      console.error('Error creating tag span(s):', error)
    } finally {
      isProcessing.value = false
    }
  }

  const updateTagSpan = async (
    data: Parameters<
      typeof api.updateTagSpanApiTagSpansUpdatePatch
    >[0]['tagSpanUpdateSeparateRequest']
  ) => {
    isProcessing.value = true
    try {
      const response = await api.updateTagSpanApiTagSpansUpdatePatch({
        tagSpanUpdateSeparateRequest: data
      })
      console.log('Tag updated successfully:', response)
    } catch (error) {
      console.error('Error updating tag:', error)
    } finally {
      isProcessing.value = false
    }
  }

  const deleteTagSpan = async (
    spanId: Parameters<
      typeof api.deleteTagSpanApiTagSpansSpanIdDelete
    >[0]['spanId']
  ) => {
    isProcessing.value = true
    try {
      await api.deleteTagSpanApiTagSpansSpanIdDelete({
        spanId
      })
      console.log('Tag span deleted successfully')
    } catch (error) {
      console.error('Error deleting tag span:', error)
    } finally {
      isProcessing.value = false
    }
  }

  const getTagsForCollection = async () => {
    isProcessing.value = true
    try {
      const response = await api.getTagsApiTagsGet()
      console.log('Fetched tags for collection:', response)
      availableTags.value = response.tagsLst
    } catch (error) {
      console.error('Error fetching tags for collection:', error)
      availableTags.value = []
    } finally {
      isProcessing.value = false
    }
  }

  return {
    // State
    collectionChunks,
    tagSpans,
    isProcessing,
    availableTags,

    // Methods
    getCollectionChunksPaged,
    fetchTagSpansForChunk,
    fetchTagSpansMapForChunks,
    getTagSpans,
    createTagSpan,
    updateTagSpan,
    deleteTagSpan,
    getTagsForCollection
  }
}
