import type { CollectionChunk } from 'src/generated/api'

// Offset helpers of the document reader. A span or selection is anchored on its first
// chunk; its `end` is measured across the concatenated text of the consecutive known
// chunks (displayed and hidden ones), as in src/features/annotations/spanOffsets.ts.

export interface ChunkParagraph {
  chunks: CollectionChunk[]
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
export function groupParagraphs (chunks: CollectionChunk[]): ChunkParagraph[] {
  const paragraphs: ChunkParagraph[] = []
  let currentGroup: CollectionChunk[] = []

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

/** Displayed and hidden chunks without duplicates, in document order. */
export function knownChunksInOrder (displayed: CollectionChunk[], hidden: CollectionChunk[]): CollectionChunk[] {
  return [...displayed, ...hidden]
    .filter((c, i, arr) => arr.findIndex((x) => x.id === c.id) === i)
    .sort((a, b) => a.order - b.order)
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
 * Assigns each marker the first column where it does not overlap the previous marker
 * (4 px apart), in top order. Sorts `items` in place.
 */
export function assignColumns<T extends { top: number, height: number, column: number }> (items: T[]): T[] {
  items.sort((a, b) => a.top - b.top)
  const columnBottoms: number[] = []
  for (const item of items) {
    const free = columnBottoms.findIndex((bottom) => item.top >= bottom + 4)
    item.column = free === -1 ? columnBottoms.length : free
    columnBottoms[item.column] = item.top + item.height
  }
  return items
}

/**
 * Resolves a DOM selection endpoint to its chunk and character offset, using the
 * `data-start` of the enclosing text segment and the `data-chunk-id` of its chunk.
 */
export function resolveSelectionEndpoint (node: Node, offset: number): { chunkId: string, charOffset: number } | null {
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
