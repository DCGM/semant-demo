import { useApi } from 'src/composables/useApi'
import type { TagSpan, TagSpans, PostSpan, PatchSpan } from 'src/models/tagSpans'
import type { BulkUpdateSpansResponse } from 'src/generated/api'

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

    /** Best effort: ``spans`` holds the updated spans, ``failed`` the rest. */
    bulkUpdate: async (spanIds: string[], patch: PatchSpan): Promise<BulkUpdateSpansResponse> => {
      return api.bulkUpdateTagSpansApiTagSpansBulkUpdatePost({
        bulkUpdateSpansRequest: {
          spanIds,
          update: patch
        }
      })
    },

    delete: async (spanId: string): Promise<void> => {
      return api.deleteTagSpanApiTagSpansSpanIdDelete({ spanId })
    }
  }
}
