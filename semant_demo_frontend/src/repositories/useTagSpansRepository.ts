import { useApi } from 'src/composables/useApi'
import type { TagSpan, TagSpans, PostSpan, PatchSpan } from 'src/models/tagSpans'

export function useTagSpansRepository() {
  const api = useApi().default

  return {
    getByChunkIdInCollection: async (chunkId: string, collectionId: string): Promise<TagSpans> => {
      return api.readTagSpansApiTagSpansGet({ chunkId, collectionId })
    },

    getByChunkIdsInCollection: async (chunkIds: string[], collectionId: string): Promise<Record<string, TagSpans>> => {
      return api.readTagSpansBatchApiTagSpansBatchPost({
        tagSpanBatchRequest: {
          chunkIds,
          collectionId
        }
      })
    },

    create: async (span: PostSpan): Promise<TagSpan> => {
      return api.createTagSpanApiTagSpansPost({
        postSpan: span
      })
    },

    update: async (spanId: string, tagSpan: PatchSpan): Promise<TagSpan> => {
      return api.updateTagSpanApiTagSpansSpanIdPatch({
        spanId,
        patchSpan: tagSpan
      })
    },

    bulkUpdate: async (spanIds: string[], patch: PatchSpan): Promise<TagSpans> => {
      const res = await api.bulkUpdateTagSpansApiTagSpansBulkUpdatePost({
        bulkUpdateSpansRequest: {
          spanIds,
          update: patch
        }
      })
      return res.spans
    },

    delete: async (spanId: string): Promise<void> => {
      return api.deleteTagSpanApiTagSpansSpanIdDelete({ spanId })
    }
  }
}
