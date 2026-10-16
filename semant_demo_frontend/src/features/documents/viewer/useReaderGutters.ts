import { ref, watch, type Ref } from 'vue'
import { SpanType, type CollectionChunk, type TagSpan } from 'src/generated/api'
import type { SpanMarker } from 'src/features/annotations/AnnotationGutterTypes'
import { projectSpan } from 'src/features/annotations/spanOffsets'
import { assignColumns, knownChunksInOrder } from './readerOffsets'

/** A displayed chunk's row in the chunk gutter. */
export interface ChunkRow {
  chunkId: string
  order: number
  top: number
  height: number
}

/**
 * Positions of the reader's gutters, measured from the rendered text: a row per displayed
 * chunk and a marker per shown span. Positions are relative to the top of the reader card
 * (`.paper-card`), which the gutters are aligned with. Call `relayout` after the text
 * changed and was rendered.
 */
export function useReaderGutters (
  textEl: Ref<HTMLElement | null>,
  displayChunks: Ref<CollectionChunk[]>,
  hiddenChunks: Ref<CollectionChunk[]>,
  spansByChunkId: () => Record<string, TagSpan[]>,
  showsSpan: (span: TagSpan) => boolean
) {
  const spanMarkers = ref<SpanMarker[]>([])
  const chunkRows = ref<ChunkRow[]>([])

  const cardOf = (container: HTMLElement) => container.closest('.paper-card') as HTMLElement | null

  function relayoutChunkRows () {
    const container = textEl.value
    const cardEl = container && cardOf(container)
    if (!container || !cardEl) { chunkRows.value = []; return }
    const cardRect = cardEl.getBoundingClientRect()
    const rows: ChunkRow[] = []

    for (const chunk of displayChunks.value) {
      const chunkEl = container.querySelector(`[data-chunk-id="${chunk.id}"]`) as HTMLElement | null
      if (!chunkEl) continue
      const rect = chunkEl.getBoundingClientRect()
      rows.push({
        chunkId: chunk.id,
        order: chunk.order,
        top: rect.top - cardRect.top,
        height: Math.max(rect.height, 24)
      })
    }
    chunkRows.value = rows
  }

  function relayout () {
    const container = textEl.value
    const cardEl = container && cardOf(container)
    if (!container || !cardEl) { spanMarkers.value = []; return }
    const cardRect = cardEl.getBoundingClientRect()
    const markers: SpanMarker[] = []

    // Use all known chunks (display + hidden) so a marker bridges gaps caused by removed chunks.
    const known = knownChunksInOrder(displayChunks.value, hiddenChunks.value)

    for (const chunk of displayChunks.value) {
      const anchor = known.findIndex(c => c.id === chunk.id)
      if (anchor === -1) continue

      for (const span of spansByChunkId()[chunk.id] || []) {
        if (!span.id || !showsSpan(span)) continue

        let minTop = Infinity
        let maxBottom = -Infinity
        for (const part of projectSpan(known, anchor, span.start, span.end)) {
          // A hidden chunk has no element; it only shifts the offsets of the next ones.
          const chunkEl = container.querySelector(`[data-chunk-id="${known[part.chunk].id}"]`) as HTMLElement | null
          if (!chunkEl) continue
          for (const segEl of Array.from(chunkEl.querySelectorAll<HTMLElement>('.text-segment'))) {
            const segStart = parseInt(segEl.dataset.start || '0')
            const segEnd = parseInt(segEl.dataset.end || '0')
            if (segStart < part.end && segEnd > part.start) {
              const rect = segEl.getBoundingClientRect()
              minTop = Math.min(minTop, rect.top - cardRect.top)
              maxBottom = Math.max(maxBottom, rect.bottom - cardRect.top)
            }
          }
        }
        if (minTop === Infinity) continue

        markers.push({
          spanId: span.id,
          chunkId: chunk.id,
          tagId: span.tagId,
          start: span.start,
          end: span.end,
          top: minTop,
          height: Math.max(maxBottom - minTop, 20),
          column: 0,
          isAuto: span.type === SpanType.auto
        })
      }
    }

    spanMarkers.value = assignColumns(markers)
    relayoutChunkRows()
  }

  // When the span gutter appears or disappears the reader card width changes, text
  // reflows and chunk heights change → re-measure the chunk rows.
  watch(spanMarkers, (markers, oldMarkers) => {
    if ((markers.length > 0) !== (oldMarkers.length > 0)) {
      requestAnimationFrame(() => relayoutChunkRows())
    }
  })

  return { spanMarkers, chunkRows, relayout }
}
