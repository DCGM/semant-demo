import type { CollectionChunk } from 'src/generated/api'
import { knownChunksInOrder, reuseIfSameReferences } from 'src/features/annotations/spanOffsets'

export { knownChunksInOrder }
// Offset helpers of the document reader. A span or selection is anchored on its first
// chunk; its `end` is measured across the concatenated text of the consecutive known
// chunks (displayed and hidden ones), as in src/features/annotations/spanOffsets.ts.

/** What the text pane needs of a chunk: its canonical text and its place in the document. */
export type TextChunk = Pick<CollectionChunk, 'id' | 'order' | 'text' | 'endParagraph'>

/**
 * A position in the canonical text: a UTF-16 offset into one chunk's stored text, as
 * annotation offsets are.
 */
export interface TextPoint {
  chunkId: string
  charOffset: number
}

export interface ChunkParagraph<T extends TextChunk = CollectionChunk> {
  chunks: T[]
  /** Order of the last chunk before a gap in chunk order, when the paragraph ends at one. */
  gapAfter: number | null
  /** Order of the first chunk after that gap. */
  gapBefore: number | null
}

/** Offsets anchored on a chunk; `end` may reach into the following chunks. */
export interface ChunkRange {
  chunkId: string
  start: number
  end: number
}

/**
 * Groups the displayed chunks into paragraphs. A paragraph ends at a chunk marked
 * `endParagraph` and at a gap in chunk order, so the gap controls go between paragraphs.
 */
export function groupParagraphs<T extends TextChunk> (chunks: T[]): ChunkParagraph<T>[] {
  const paragraphs: ChunkParagraph<T>[] = []
  let currentGroup: T[] = []

  for (let i = 0; i < chunks.length; i++) {
    const chunk = chunks[i]
    currentGroup.push(chunk)

    const nextChunk = chunks[i + 1]
    const hasGap = nextChunk != null && nextChunk.order > chunk.order + 1

    if (chunk.endParagraph || hasGap || !nextChunk) {
      paragraphs.push({
        chunks: [...currentGroup],
        gapAfter: hasGap ? chunk.order : null,
        gapBefore: hasGap ? nextChunk.order : null
      })
      currentGroup = []
    }
  }

  if (currentGroup.length) {
    paragraphs.push({ chunks: currentGroup, gapAfter: null, gapBefore: null })
  }

  return paragraphs
}

/** The number of chunks missing in the gap a paragraph ends at; 0 when it ends at none. */
export function gapSize (paragraph: ChunkParagraph<TextChunk>): number {
  if (paragraph.gapAfter === null || paragraph.gapBefore === null) return 0
  return paragraph.gapBefore - paragraph.gapAfter - 1
}

/** The text of the divider at a gap of `count` missing chunks. */
export function missingChunksText (count: number): string {
  return count === 1 ? '1 chunk not shown' : `${count} chunks not shown`
}

/**
 * Splits a range anchored on a chunk into the part of it in each chunk it covers: `end`
 * continues into the following chunks of `chunks` while their orders are consecutive.
 * Chunks it does not cover, or that are not in `chunks`, get no entry.
 */
export function rangeByChunk (
  range: ChunkRange, chunks: TextChunk[]
): Record<string, { start: number, end: number }> {
  const result: Record<string, { start: number, end: number }> = {}
  const startIdx = chunks.findIndex((c) => c.id === range.chunkId)
  if (startIdx === -1) return result
  let offset = 0 // where the current chunk starts, measured from the start of the anchor chunk
  for (let i = startIdx; i < chunks.length; i++) {
    if (i > startIdx && chunks[i].order !== chunks[i - 1].order + 1) break
    const len = (chunks[i].text ?? '').length
    const start = Math.max(0, range.start - offset)
    const end = Math.min(len, range.end - offset)
    if (end > start) result[chunks[i].id] = { start, end }
    offset += len
    if (offset >= range.end) break
  }
  return result
}

/**
 * The span a click on tagged text opens: the shortest one, an approved span before an AI
 * suggestion of the same length, then the earlier one.
 */
export function shortestMarker<T extends { start: number, end: number, isAuto: boolean }> (markers: T[]): T | null {
  let best: T | null = null
  for (const m of markers) {
    if (!best) { best = m; continue }
    const diff = (m.end - m.start) - (best.end - best.start)
    if (diff < 0 || (diff === 0 && (Number(m.isAuto) - Number(best.isAuto) || m.start - best.start) < 0)) best = m
  }
  return best
}

/**
 * Maps a selection onto the displayed chunks it overlaps. Hidden chunks are skipped and
 * the offsets are re-measured across the concatenated text of the returned chunks.
 * Returns null when no displayed chunk overlaps the selection.
 */
export function selectionInDisplayedChunks (
  selection: ChunkRange, displayed: CollectionChunk[], hidden: CollectionChunk[]
): { chunkIds: string[], start: number, end: number } | null {
  const visibleIds = new Set(displayed.map((c) => c.id))
  const known = knownChunksInOrder(displayed, hidden)
  const startIdx = known.findIndex((c) => c.id === selection.chunkId)
  if (startIdx === -1) return null

  const chunkIds: string[] = []
  let assembledLen = 0
  let start = -1
  let end = -1
  let cursor = 0 // offset of the current chunk in the concatenation of known chunks
  for (let i = startIdx; i < known.length; i++) {
    if (i > startIdx && known[i].order !== known[i - 1].order + 1) break
    const c = known[i]
    const len = (c.text ?? '').length
    const chunkStartGlobal = cursor
    const chunkEndGlobal = cursor + len
    cursor = chunkEndGlobal

    if (chunkStartGlobal >= selection.end) break
    if (chunkEndGlobal <= selection.start) continue
    if (!visibleIds.has(c.id)) continue

    const localStart = Math.max(0, selection.start - chunkStartGlobal)
    const localEnd = Math.min(len, selection.end - chunkStartGlobal)

    if (start === -1) start = assembledLen + localStart
    end = assembledLen + localEnd
    chunkIds.push(c.id)
    assembledLen += len
  }

  if (!chunkIds.length || start < 0 || end <= start) return null
  return { chunkIds, start, end }
}

/** The text a selection covers, continuing into later chunks when it is longer than its first chunk. */
export function selectionText (selection: ChunkRange, chunks: CollectionChunk[]): string {
  const startChunk = chunks.find((c) => c.id === selection.chunkId)
  let assembled = startChunk?.text ?? ''
  if (startChunk && selection.end > assembled.length) {
    const ordered = chunks
      .filter((c) => c.order > startChunk.order)
      .sort((a, b) => a.order - b.order)
    for (const c of ordered) {
      assembled += c.text ?? ''
      if (assembled.length >= selection.end) break
    }
  }
  const start = Math.max(0, Math.min(selection.start, assembled.length))
  const end = Math.max(start, Math.min(selection.end, assembled.length))
  return assembled.slice(start, end)
}

/**
 * Assigns columns from the longest marker down (ties by top): each takes the first column
 * where it does not overlap a marker already there (4 px apart). Of the markers sharing
 * lines, the longer one is nearer column 0, next to the text. Sorts `items` in place by
 * top.
 */
export function assignColumns<T extends { top: number, height: number, column: number }> (items: T[]): T[] {
  const placed: T[][] = []
  const overlaps = (a: T, b: T) => a.top < b.top + b.height + 4 && b.top < a.top + a.height + 4
  for (const item of [...items].sort((a, b) => b.height - a.height || a.top - b.top)) {
    const free = placed.find((column) => !column.some((other) => overlaps(item, other)))
    if (free) {
      item.column = placed.indexOf(free)
      free.push(item)
    } else {
      item.column = placed.length
      placed.push([item])
    }
  }
  return items.sort((a, b) => a.top - b.top)
}

/**
 * Resolves a DOM selection endpoint to its chunk and character offset, using the
 * `data-start` of the enclosing text segment and the `data-chunk-id` of its chunk.
 */
export function resolveSelectionEndpoint (node: Node, offset: number): TextPoint | null {
  let segmentEl: HTMLElement | null = null
  let current: Node | null = node
  while (current) {
    if (current instanceof HTMLElement && current.dataset.start !== undefined) {
      segmentEl = current
      break
    }
    current = current.parentElement
  }
  if (!segmentEl) return null

  let chunkEl: HTMLElement | null = segmentEl
  while (chunkEl && !chunkEl.dataset.chunkId) {
    chunkEl = chunkEl.parentElement
  }
  if (!chunkEl) return null

  const segStart = parseInt(segmentEl.dataset.start || '0', 10)
  const charOffset = node.nodeType === Node.TEXT_NODE ? segStart + offset : segStart
  return { chunkId: chunkEl.dataset.chunkId!, charOffset }
}

/**
 * Filter projected spans for the reader and preserve array references
 * for chunks whose visible spans have not changed.
 */
export function memoizeVisibleSpansByChunkId<T> (
  chunks: Pick<CollectionChunk, 'id'>[],
  getSpans: (chunkId: string) => T[],
  isVisible: (span: T) => boolean,
  previous: Record<string, T[]>
): Record<string, T[]> {
  const next: Record<string, T[]> = {}

  for (const chunk of chunks) {
    const filtered = getSpans(chunk.id).filter(isVisible)
    next[chunk.id] = reuseIfSameReferences(previous[chunk.id], filtered)
  }

  return next
}
