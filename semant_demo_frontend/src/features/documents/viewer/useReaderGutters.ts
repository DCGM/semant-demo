import { ref, watch, type Ref } from 'vue'
import { SpanType, type CollectionChunk, type TagSpan } from 'src/generated/api'
import type { SpanMarker } from 'src/features/annotations/AnnotationGutterTypes'
import { assignColumns } from './readerOffsets'

/** A displayed chunk's row in the chunk gutter. */
export interface ChunkRow {
  chunkId: string
  order: number
  top: number
  height: number
}

/** A rendered text segment of a chunk and its offsets in the chunk text. */
interface TextSegment {
  el: HTMLElement
  start: number
  end: number
}

/**
 * The index of the first segment ending after `offset` (`segments.length` if none);
 * `segments` are consecutive, in text order.
 */
export function firstSegmentEndingAfter (segments: readonly { end: number }[], offset: number): number {
  let lo = 0
  let hi = segments.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (segments[mid]!.end > offset) hi = mid
    else lo = mid + 1
  }
  return lo
}

/**
 * Positions of the reader's gutters, measured from the rendered text:
 * a row per displayed chunk and a marker per shown annotation.
 *
 * Projected spans come from useAnnotations and already account for
 * hidden chunks. This composable only measures their DOM positions
 * and combines cross-chunk parts into one gutter marker.
 *
 * Positions are relative to the top of the reader card (`.paper-card`).
 * Call `relayout` after the text changed and was rendered.
 */
export function useReaderGutters (
  textEl: Ref<HTMLElement | null>,
  displayChunks: Ref<CollectionChunk[]>,
  projectedSpansForChunk: (chunkId: string) => TagSpan[],
  showsSpan: (span: TagSpan) => boolean,
  measureChunkRows: () => boolean = () => true
) {
  const spanMarkers = ref<SpanMarker[]>([])
  const chunkRows = ref<ChunkRow[]>([])

  const cardOf = (container: HTMLElement) =>
    container.closest('.paper-card') as HTMLElement | null

  const chunkElementsOf = (container: HTMLElement): Map<string, HTMLElement> => {
    const result = new Map<string, HTMLElement>()

    for (const element of Array.from(
      container.querySelectorAll<HTMLElement>('[data-chunk-id]')
    )) {
      const chunkId = element.dataset.chunkId
      if (chunkId) result.set(chunkId, element)
    }

    return result
  }

  function relayoutChunkRows (
    chunkElements?: Map<string, HTMLElement>,
    knownCardRect?: DOMRect
  ) {
    // Never retain positions from a previously visible chunk gutter.
    if (!measureChunkRows()) {
      chunkRows.value = []
      return
    }

    const container = textEl.value
    const cardEl = container && cardOf(container)

    if (!container || !cardEl) {
      chunkRows.value = []
      return
    }

    const cardRect = knownCardRect ?? cardEl.getBoundingClientRect()
    const elements = chunkElements ?? chunkElementsOf(container)
    const rows: ChunkRow[] = []

    for (const chunk of displayChunks.value) {
      const chunkEl = elements.get(chunk.id)
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

    if (!container || !cardEl) {
      spanMarkers.value = []
      chunkRows.value = []
      return
    }

    const cardRect = cardEl.getBoundingClientRect()

    // Index DOM chunks once instead of querying the whole document
    // for every span part.
    const chunkElements = chunkElementsOf(container)

    // Load text segments lazily, only for chunks containing shown spans, with their
    // offsets parsed once. Segments follow each other in text order.
    const segmentsByChunkId = new Map<string, TextSegment[]>()

    const segmentsFor = (chunkId: string): TextSegment[] => {
      const cached = segmentsByChunkId.get(chunkId)
      if (cached) return cached

      const chunkEl = chunkElements.get(chunkId)
      const segments = chunkEl
        ? Array.from(chunkEl.querySelectorAll<HTMLElement>('.text-segment'), (el) => ({
          el,
          start: parseInt(el.dataset.start || '0', 10),
          end: parseInt(el.dataset.end || '0', 10)
        }))
        : []

      segmentsByChunkId.set(chunkId, segments)
      return segments
    }

    interface MarkerExtent {
      anchor: TagSpan | null
      minTop: number
      maxBottom: number
    }

    // A cross-chunk annotation has several projected parts but
    // must produce only one gutter marker.
    const extentsBySpanId = new Map<string, MarkerExtent>()

    for (const chunk of displayChunks.value) {
      const projectedSpans = projectedSpansForChunk(chunk.id)

      for (const span of projectedSpans) {
        if (!span.id || !showsSpan(span)) continue

        let extent = extentsBySpanId.get(span.id)

        if (!extent) {
          extent = { anchor: null, minTop: Infinity, maxBottom: -Infinity }

          extentsBySpanId.set(span.id, extent)
        }

        // The anchor entry retains the original chunk ID and offsets.
        // Only spans anchored in a displayed chunk create markers.
        if (span.chunkId === chunk.id) {
          extent.anchor = span
        }

        // Hidden chunks have no DOM elements. Their text lengths were
        // already accounted for by useAnnotations during projection.
        // Only the segments the span overlaps: from the first one ending after its start
        // (one pass per span over every segment was quadratic in long chunks, #464).
        const segments = segmentsFor(chunk.id)
        for (let i = firstSegmentEndingAfter(segments, span.start); i < segments.length; i++) {
          const seg = segments[i]!
          if (seg.start >= span.end) break

          if (seg.end > span.start) {
            const rect = seg.el.getBoundingClientRect()

            extent.minTop = Math.min(
              extent.minTop,
              rect.top - cardRect.top
            )

            extent.maxBottom = Math.max(
              extent.maxBottom,
              rect.bottom - cardRect.top
            )
          }
        }
      }
    }

    const markers: SpanMarker[] = []

    for (const [spanId, extent] of extentsBySpanId) {
      const span = extent.anchor

      // Ignore spans without a displayed anchor or visible text geometry.
      if (!span || extent.minTop === Infinity) continue

      markers.push({
        spanId,
        chunkId: span.chunkId,
        tagId: span.tagId,
        start: span.start,
        end: span.end,
        top: extent.minTop,
        height: Math.max(extent.maxBottom - extent.minTop, 20),
        column: 0,
        isAuto: span.type === SpanType.auto
      })
    }

    spanMarkers.value = assignColumns(markers)

    // Reuse the same DOM lookup for chunk-row measurements.
    relayoutChunkRows(chunkElements, cardRect)
  }

  // When the span gutter appears or disappears the reader card width changes,
  // text reflows and chunk heights change -> re-measure the chunk rows.
  watch(spanMarkers, (markers, oldMarkers) => {
    if ((markers.length > 0) !== (oldMarkers.length > 0)) {
      requestAnimationFrame(() => relayoutChunkRows())
    }
  })

  return { spanMarkers, chunkRows, relayout, relayoutChunkRows }
}
