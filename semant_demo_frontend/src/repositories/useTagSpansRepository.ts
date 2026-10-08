import { useApi } from 'src/shared/api'
import type { TagSpans, PostSpan, PatchSpan } from 'src/models/tagSpans'
import type { BulkUpdateSpansResponse, TagSpanWriteResult, WriteResult } from 'src/generated/api'

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

    /** The saved span; ``outcome`` is partial when its search tag could not be updated. */
    create: async (span: PostSpan): Promise<TagSpanWriteResult> => {
      return api.createTagSpanApiTagSpansPost({
        postSpan: span
      })
    },

    /** The updated span; ``outcome`` is partial when its search tag could not be updated. */
    update: async (spanId: string, tagSpan: PatchSpan): Promise<TagSpanWriteResult> => {
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

    /** ``outcome`` is partial when the span was deleted but its search tag was not updated. */
    delete: async (spanId: string): Promise<WriteResult> => {
      return api.deleteTagSpanApiTagSpansSpanIdDelete({ spanId })
    }
  }
}
