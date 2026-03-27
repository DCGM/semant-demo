import { useApi } from 'src/composables/useApi'
import type { TagSpan } from 'src/generated/api'
import { ref } from 'vue'

export type ChResponse = {
  uuid: string
  properties: {
    text: string
  }
}

export type Ch = {
  id: string
  text: string
}

export function useTagging() {
  const api = useApi().default

  const chunk = ref<Ch | null>(null)
  const tagSpans = ref<TagSpan[]>([])
  const isProcessing = ref(false)

  const getChunk = async () => {
    isProcessing.value = true
    try {
      const response =
        (await api.getFirstChunkApiGetFirstChunkGet()) as unknown as ChResponse
      chunk.value = {
        id: response.uuid,
        text: response.properties.text
      }
      console.log('Fetched chunk:', response)
    } catch (error) {
      console.error('Error fetching chunk:', error)
    } finally {
      isProcessing.value = false
    }
  }

  const getTagSpans = async (
    chunkId: Parameters<
      typeof api.readTagSpansApiTagSpansSeparateChunkIdGet
    >[0]['chunkId']
  ) => {
    isProcessing.value = true
    try {
      const response = await api.readTagSpansApiTagSpansSeparateChunkIdGet({
        chunkId
      })
      tagSpans.value = response
      console.log('Fetched tag spans:', response)
    } catch (error) {
      console.error('Error fetching tag spans:', error)
    } finally {
      isProcessing.value = false
    }
  }

  const createTagSpan = async (
    data: Parameters<
      typeof api.upsertTagSpansSeparateApiTagSpansSeparatePost
    >[0]['tagSpanCreateSeparateRequest']
  ) => {
    await api
      .upsertTagSpansSeparateApiTagSpansSeparatePost({
        tagSpanCreateSeparateRequest: {
          span: data.span
        }
      })
      .then((response) => {
        console.log('Tag span(s) created successfully:', response)
      })
      .catch((error) => {
        console.error('Error creating tag span(s):', error)
      })
  }

  const updateTagSpan = async (
    data: Parameters<
      typeof api.updateTagSpanSeparateApiTagSpansUpdateSeparatePatch
    >[0]['tagSpanUpdateSeparateRequest']
  ) => {
    isProcessing.value = true
    try {
      const response =
        await api.updateTagSpanSeparateApiTagSpansUpdateSeparatePatch({
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
      typeof api.deleteTagSpanSeparateApiTagSpansSeparateSpanIdDelete
    >[0]['spanId']
  ) => {
    await api
      .deleteTagSpanSeparateApiTagSpansSeparateSpanIdDelete({
        spanId
      })
      .then(() => {
        console.log('Tag span deleted successfully')
      })
      .catch((error) => {
        console.error('Error deleting tag span:', error)
      })
  }

  return {
    // State
    chunk,
    tagSpans,
    isProcessing,

    // Methods
    getChunk,
    getTagSpans,
    createTagSpan,
    updateTagSpan,
    deleteTagSpan
  }
}
