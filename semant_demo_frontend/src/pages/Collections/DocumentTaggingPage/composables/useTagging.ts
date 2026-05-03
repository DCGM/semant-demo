import { useApi } from 'src/composables/useApi'
import { TagSpan } from 'src/generated/api/models/TagSpan'
import { ref } from 'vue'
import { AvailableTag } from '../components/ChunkTagAnnotator.vue'
import { Tag } from 'src/generated/api/models/Tag'
import { ReadTagSpansApiTagSpansGetRequest } from 'src/generated/api'

export function useTagging() {
  const api = useApi().default
  const documentDetail =
    ref<
      Awaited<
        ReturnType<
          typeof api.fetchDocumentChunksApiDocumentsDocumentIdCollectionIdChunksGet
        >
      >
    >()

  const tagSpans = ref<TagSpan[]>([])
  const isProcessing = ref(false)
  const availableTags = ref<AvailableTag[]>([])
  const collectionTags = ref<Tag[]>([])
  const discoveredTopicChunkIds = ref<string[]>([])

  const getDocumentDetail = async (
    documentId: Parameters<
      typeof api.fetchDocumentChunksApiDocumentsDocumentIdCollectionIdChunksGet
    >[0]['documentId'],
    collectionId: Parameters<
      typeof api.fetchDocumentChunksApiDocumentsDocumentIdCollectionIdChunksGet
    >[0]['collectionId']
  ) => {
    isProcessing.value = true
    try {
      const response =
        await api.fetchDocumentChunksApiDocumentsDocumentIdCollectionIdChunksGet(
          {
            collectionId,
            documentId
          }
        )

      documentDetail.value = response
      console.log('Fetched document detail:', response)
      return response
    } catch (error) {
      console.error('Error fetching document detail:', error)
      documentDetail.value = undefined
      return undefined
    } finally {
      isProcessing.value = false
    }
  }

  const fetchTagSpansForChunk = async ({
    chunkId,
    collectionId
  }: ReadTagSpansApiTagSpansGetRequest): Promise<TagSpan[]> => {
    try {
      const response = await api.readTagSpansApiTagSpansGet({
        chunkId,
        collectionId
      })
      return response
    } catch (error) {
      console.error('Error fetching tag spans:', error)
      return []
    }
  }

  const fetchTagSpansMapForChunks = async (
    chunkIds: string[],
    collectionId: string
  ) => {
    const pairs = await Promise.all(
      chunkIds.map(async (chunkId) => {
        const spans = await fetchTagSpansForChunk({
          chunkId,
          collectionId
        })
        return [chunkId, spans] as const
      })
    )

    return pairs.reduce<Record<string, TagSpan[]>>((acc, [chunkId, spans]) => {
      acc[chunkId] = spans
      return acc
    }, {})
  }

  const getTagSpans = async (
    chunkId: ReadTagSpansApiTagSpansGetRequest['chunkId'],
    collectionId: ReadTagSpansApiTagSpansGetRequest['collectionId']
  ): Promise<TagSpan[]> => {
    isProcessing.value = true
    try {
      const response = await fetchTagSpansForChunk({ chunkId, collectionId })
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
    span: Parameters<typeof api.createTagSpanApiTagSpansPost>[0]['postSpan']
  ) => {
    isProcessing.value = true
    try {
      const response = await api.createTagSpanApiTagSpansPost({
        postSpan: span
      })
      console.log('Tag span(s) created successfully:', response)
    } catch (error) {
      console.error('Error creating tag span(s):', error)
    } finally {
      isProcessing.value = false
    }
  }

  const updateTagSpan = async (
    data: Parameters<typeof api.updateTagSpanApiTagSpansSpanIdPatch>[0]
  ) => {
    isProcessing.value = true
    try {
      const response = await api.updateTagSpanApiTagSpansSpanIdPatch({
        patchSpan: data.patchSpan,
        spanId: data.spanId
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

  const getTagsForCollection = async (
    collectionId: Parameters<
      typeof api.getCollectionTagsApiCollectionsCollectionIdTagsGet
    >[0]['collectionId']
  ) => {
    isProcessing.value = true
    try {
      const response =
        await api.getCollectionTagsApiCollectionsCollectionIdTagsGet({
          collectionId
        })
      collectionTags.value = response
      availableTags.value = response.map((tag) => ({
        tagUuid: tag.id,
        tagName: tag.name,
        tagColor: tag.color,
        tagShorthand: tag.shorthand,
        tagPictogram: tag.pictogram,
        tagDefinition: tag.definition || undefined,
        tagExamples: tag.examples || undefined
      }))
    } catch (error) {
      console.error('Error fetching tags for collection:', error)
      collectionTags.value = []
      availableTags.value = []
    } finally {
      isProcessing.value = false
    }
  }

  const addChunkToCollection = async ({
    chunkId,
    collectionId
  }: Parameters<
    typeof api.addChunk2CollectionApiUserCollectionChunksPost
  >[0]['chunk2CollectionReq']) => {
    try {
      const response = await api.addChunk2CollectionApiUserCollectionChunksPost(
        {
          chunk2CollectionReq: {
            chunkId,
            collectionId
          }
        }
      )
      console.log('Chunk added to collection successfully:', response)
      return response
    } catch (error) {
      console.error('Error adding chunk to collection:', error)
      return undefined
    }
  }

  const removeChunkFromCollection = async ({
    chunkId,
    collectionId
  }: Parameters<
    typeof api.removeChunkFromCollectionApiUserCollectionChunksRemovePost
  >[0]['chunk2CollectionReq']) => {
    try {
      const response =
        await api.removeChunkFromCollectionApiUserCollectionChunksRemovePost({
          chunk2CollectionReq: {
            chunkId,
            collectionId
          }
        })
      console.log('Chunk removed from collection successfully:', response)
      return response
    } catch (error) {
      console.error('Error removing chunk from collection:', error)
      return undefined
    }
  }

  const suggestAnnotations = async ({
    chunks,
    tags
  }: Parameters<
    typeof api.proposeTagsApiProposeTagsPost
  >[0]['autoAnnotationSuggestionRequest']) => {
    try {
      const response = await api.proposeTagsApiProposeTagsPost({
        autoAnnotationSuggestionRequest: {
          chunks,
          tags
        }
      })
      console.log('Auto-annotation suggestions fetched successfully:', response)
      return response
    } catch (error) {
      console.error('Error fetching auto-annotation suggestions:', error)
      return {
        suggestions: []
      }
    }
  }

  const approveTagSpan = async ({
    chunkID,
    tagID,
    collectionID,
    spanID,
    start,
    end
  }: Parameters<
    typeof api.approveSelectedTagChunkApiTagApprovePut
  >[0]['approveTagReq']) => {
    isProcessing.value = true
    try {
      const response = await api.approveSelectedTagChunkApiTagApprovePut({
        approveTagReq: {
          chunkID,
          tagID,
          collectionID,
          spanID,
          start,
          end
        }
      })
      return response
    } catch (error) {
      console.error('Error approving tag span:', error)
      return undefined
    } finally {
      isProcessing.value = false
    }
  }

  const declineTagSpan = async ({
    chunkID,
    tagID,
    collectionID,
    spanID,
    start,
    end
  }: Parameters<
    typeof api.approveSelectedTagChunkApiTagDisapprovePut
  >[0]['approveTagReq']) => {
    isProcessing.value = true
    try {
      const response = await api.approveSelectedTagChunkApiTagDisapprovePut({
        approveTagReq: {
          chunkID,
          tagID,
          collectionID,
          spanID,
          start,
          end
        }
      })
      return response
    } catch (error) {
      console.error('Error declining tag span:', error)
      return undefined
    } finally {
      isProcessing.value = false
    }
  }

  const proposeBestTag = async ({
    text,
    tags
  }: Parameters<
    typeof api.proposeBestTagApiProposeBestTagPost
  >[0]['bestTagProposalRequest']) => {
    try {
      const response = await api.proposeBestTagApiProposeBestTagPostRaw({
        bestTagProposalRequest: {
          text,
          tags
        }
      })

      return await response.raw.json()
    } catch (error) {
      console.error('Error proposing best tag:', error)
      return undefined
    }
  }

  return {
    // State
    documentDetail,
    tagSpans,
    isProcessing,
    availableTags,
    collectionTags,
    discoveredTopicChunkIds,

    // Methods
    getDocumentDetail,
    fetchTagSpansForChunk,
    fetchTagSpansMapForChunks,
    getTagSpans,
    createTagSpan,
    updateTagSpan,
    approveTagSpan,
    declineTagSpan,
    deleteTagSpan,
    getTagsForCollection,
    addChunkToCollection,
    removeChunkFromCollection,
    suggestAnnotations,
    proposeBestTag
  }
}
