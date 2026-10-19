import { useApi } from 'src/shared/api'
import type { TagSpan, PostSpan, PatchSpan, BulkUpdateSpansResponse, TagSpanWriteResult, WriteResult } from 'src/generated/api'

export function useTagSpansRepository() {
  const api = useApi().default

  return {
    getByChunkIdInCollection: async (chunkId: string, collectionId: string): Promise<TagSpan[]> => {
      return api.readTagSpansApiTagSpansGet({ chunkId, collectionId })
    },

    getByChunkIdsInCollection: async (chunkIds: string[], collectionId: string): Promise<Record<string, TagSpan[]>> => {
      return api.readTagSpansBatchApiTagSpansBatchPost({
        tagSpanBatchRequest: {
          chunkIds,
          collectionId
        }
      })
    },

    /** The saved span; ``outcome`` is partial when its search tag could not be updated. */
    create: async (span: PostSpan): Promise<TagSpanWriteResult> => {
      return api.createTagSpanApiTagSpansPost({
        postSpan: span
      })
    },

    /**
     * The updated span; ``outcome`` is partial when its search tag could not be updated.
     * Spans are addressed within their collection: the same id in another collection is
     * not found.
     */
    update: async (spanId: string, collectionId: string, tagSpan: PatchSpan): Promise<TagSpanWriteResult> => {
      return api.updateTagSpanApiTagSpansSpanIdPatch({
        spanId,
        collectionId,
        patchSpan: tagSpan
      })
    },

    /** Best effort: ``spans`` holds the updated spans, ``failed`` the rest. */
    bulkUpdate: async (spanIds: string[], collectionId: string, patch: PatchSpan): Promise<BulkUpdateSpansResponse> => {
      return api.bulkUpdateTagSpansApiTagSpansBulkUpdatePost({
        bulkUpdateSpansRequest: {
          collectionId,
          spanIds,
          update: patch
        }
      })
    },

    /** ``outcome`` is partial when the span was deleted but its search tag was not updated. */
    delete: async (spanId: string, collectionId: string): Promise<WriteResult> => {
      return api.deleteTagSpanApiTagSpansSpanIdDelete({ spanId, collectionId })
    }
  }
}
