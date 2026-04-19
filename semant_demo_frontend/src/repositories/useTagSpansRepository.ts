import { useApi } from 'src/composables/useApi'
import type { TagSpan, TagSpans, TagSpanUpdate } from 'src/models/tagSpans'
import type { TagSpanWriteResponse } from 'src/generated/api'

export function useTagSpansRepository() {
  const api = useApi().default
  const basePath = (api as unknown as { configuration: { basePath: string } }).configuration.basePath

  return {
    getByChunkId: async (chunkId: string): Promise<TagSpans> => {
      return api.readTagSpansApiTagSpansChunkIdGet({ chunkId })
    },

    getByChunkIds: async (chunkIds: string[]): Promise<Record<string, TagSpans>> => {
      const response = await fetch(`${basePath}/api/tag_spans/batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chunk_ids: chunkIds })
      })
      if (!response.ok) {
        throw new Error(`Batch fetch failed: ${response.status}`)
      }
      return response.json()
    },

    create: async (span: TagSpan): Promise<TagSpanWriteResponse> => {
      return api.upsertTagSpansApiTagSpansPost({
        tagSpanCreateSeparateRequest: { span }
      })
    },

    update: async (spanId: string, tagSpan: TagSpanUpdate): Promise<Record<string, unknown>> => {
      return api.updateTagSpanApiTagSpansUpdatePatch({
        tagSpanUpdateSeparateRequest: { spanId, tagSpan }
      })
    },

    delete: async (spanId: string): Promise<Record<string, unknown>> => {
      return api.deleteTagSpanApiTagSpansSpanIdDelete({ spanId })
    }
  }
}
