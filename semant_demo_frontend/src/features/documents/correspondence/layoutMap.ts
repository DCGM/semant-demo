// The correspondence between canonical chunk text and the OCR lines of the page layouts
// (#544, docs/PAGE_LAYOUT.md). It is derived in the browser from a chunk's `layoutStart` and
// the page files alone: starting at the anchor's line and offset, the walk takes the lines
// of the page files in order, preceded by `\n` within a region and `\n\n` between regions
// and pages, for as many UTF-16 units as the chunk has. This is the importer's `replay`
// (semant_demo/maintenance/page_layout/anchors.py); nothing about it is stored.
//
// Text is authoritative: chunk offsets (and annotation offsets) are never changed, a line
// only tells where on the scan a piece of the text is. An `exact` anchor whose walk
// reproduces the chunk text maps characters exactly; anything else (an `approximate`
// anchor, a walk that does not reproduce the text, a page file with malformed lines) maps
// whole lines only, and a walk that reaches a page without a layout file stops there.

import type { LayoutStart } from 'src/generated/api'
import type { PageLayout } from '../scan/pageLayout'

/** One line's share of a chunk: the same text at both places, in UTF-16 units. */
export interface LayoutPiece {
  pageId: string
  lineId: string
  /** The part of the line's text, `[lineStart, lineEnd)`. */
  lineStart: number
  lineEnd: number
  /** Where it is in the chunk's text, `[start, end)`. */
  start: number
  end: number
}

/**
 * `exact`: verified character by character; `approximate`: the lines are the right ones (as
 * far as the anchor can tell) but positions inside them are not, so only whole lines may be
 * shown.
 */
export type Precision = 'exact' | 'approximate'

/** Why a map is approximate or incomplete. */
export type MapIssue =
  /** The anchor itself is approximate (the OCR text differs from the chunk text). */
  | 'approximate_anchor'
  /** An exact anchor whose walk does not reproduce the chunk text (e.g. other page files). */
  | 'text_mismatch'
  /** A page file on the way has malformed lines, so the walk may be off. */
  | 'malformed_layout'
  /** The walk reached a page without a layout file (or that failed to load). */
  | 'missing_layout'
  /** The walk reached the end of the document's pages before the end of the chunk. */
  | 'end_of_pages'

export interface ChunkLayoutMap {
  chunkId: string
  /** The chunk's length in UTF-16 units. */
  length: number
  precision: Precision
  /** In chunk order; the gaps between them are the separators. */
  pieces: LayoutPiece[]
  /** The pieces cover the chunk to its end (false: only up to `covered`). */
  complete: boolean
  covered: number
  issues: MapIssue[]
}

/** Why a chunk has no map at all. */
export type NoMapReason = 'no_anchor' | 'unknown_page' | 'missing_layout' | 'unknown_line' | 'bad_offset'

export interface MappableChunk {
  id: string
  text: string
  layoutStart?: LayoutStart | null
}

/**
 * A page's layout: the parsed file, `null` when the page has no layout file or it could not
 * be read. May reject with an abort error, which the walk passes on.
 */
export type LayoutSource = (pageId: string) => Promise<PageLayout | null>

/**
 * The map of a chunk through the pages `pageIds` (the manifest order), reading the layouts it
 * needs from `layoutOf`: the anchor's page and, when the chunk continues, the following ones.
 */
export async function mapChunk (
  chunk: MappableChunk, pageIds: readonly string[], layoutOf: LayoutSource
): Promise<ChunkLayoutMap | NoMapReason> {
  const anchor = chunk.layoutStart
  if (!anchor) return 'no_anchor'
  const first = pageIds.indexOf(anchor.pageId)
  if (first < 0) return 'unknown_page'
  const text = chunk.text ?? ''
  const length = text.length
  const issues = new Set<MapIssue>()
  if (anchor.match !== 'exact') issues.add('approximate_anchor')
  const pieces: LayoutPiece[] = []
  let position = 0
  let mismatch = false
  let started = false
  let complete = false
  let previousRegion = -1

  for (let p = first; p < pageIds.length && !complete; p++) {
    const pageId = pageIds[p]
    const layout = await layoutOf(pageId)
    if (!layout) {
      if (!started) return 'missing_layout'
      issues.add('missing_layout')
      break
    }
    if (layout.skippedLines > 0) issues.add('malformed_layout')
    let firstOnPage = true
    for (const line of layout.lines) {
      let lineStart = 0
      if (!started) {
        if (line.id !== anchor.lineId) continue
        if (!Number.isInteger(anchor.offset) || anchor.offset < 0 || anchor.offset > line.text.length) return 'bad_offset'
        started = true
        lineStart = anchor.offset
      } else {
        const separator = firstOnPage || line.regionIndex !== previousRegion ? '\n\n' : '\n'
        if (text.slice(position, position + separator.length) !== separator) mismatch = true
        position += separator.length
      }
      firstOnPage = false
      previousRegion = line.regionIndex
      if (position >= length) {
        complete = true
        break
      }
      const take = Math.min(line.text.length - lineStart, length - position)
      if (take > 0) {
        if (text.slice(position, position + take) !== line.text.slice(lineStart, lineStart + take)) mismatch = true
        pieces.push({ pageId, lineId: line.id, lineStart, lineEnd: lineStart + take, start: position, end: position + take })
        position += take
      }
      if (position >= length) {
        complete = true
        break
      }
    }
    if (!started) return 'unknown_line'
  }
  if (!complete && !issues.has('missing_layout')) issues.add('end_of_pages')
  if (mismatch && anchor.match === 'exact') issues.add('text_mismatch')
  const exact = anchor.match === 'exact' && !mismatch && !issues.has('malformed_layout')
  return {
    chunkId: chunk.id,
    length,
    precision: exact ? 'exact' : 'approximate',
    pieces,
    complete,
    covered: Math.min(position, length),
    issues: [...issues]
  }
}

/** A line of the scan to show for a text range; `start`/`end` only for an exact part. */
export interface LineTarget {
  pageId: string
  lineId: string
  /** UTF-16 offsets in the line's text, only when the map is exact. */
  start?: number
  end?: number
}

/**
 * The lines of a chunk's text `[start, end)` (UTF-16 offsets in the chunk), in order. An
 * empty range (a caret) gives the line it is in, or the next line after a separator. Exact
 * maps give the part of each line; approximate maps whole lines.
 */
export function linesForRange (map: ChunkLayoutMap, start: number, end: number): LineTarget[] {
  const lo = Math.max(0, Math.min(start, end))
  const hi = Math.max(start, end)
  const caret = hi === lo
  const pieces = caret
    // The piece the caret is in, the next one after a separator, or the last one at the end.
    ? [map.pieces.find(p => p.end > lo) ?? (lo <= map.covered ? map.pieces[map.pieces.length - 1] : undefined)]
        .filter((p): p is LayoutPiece => !!p)
    : map.pieces.filter(p => p.end > lo && p.start < hi)
  return pieces.map((piece) => {
    if (map.precision !== 'exact') return { pageId: piece.pageId, lineId: piece.lineId }
    // A caret stands for the character after it (its word on the scan).
    const from = Math.min(piece.end, Math.max(piece.start, lo))
    const to = Math.min(piece.end, Math.max(from + (caret ? 1 : 0), hi))
    return {
      pageId: piece.pageId,
      lineId: piece.lineId,
      start: piece.lineStart + from - piece.start,
      end: piece.lineStart + to - piece.start
    }
  })
}

/** Where a line of the scan is in a chunk's text. */
export interface TextHit {
  chunkId: string
  /** The line's text in the chunk, `[start, end)`. */
  start: number
  end: number
  /** The point clicked: the offset in the line mapped exactly, else the line's start. */
  point: number
  precision: Precision
  /**
   * Whether `offset` lies in this chunk's part of the line: a line can be shared by two
   * chunks, and a click belongs to the one holding the word clicked. Null without an offset.
   */
  holdsOffset: boolean | null
}

/**
 * The line `lineId` of page `pageId` in the chunk, with the UTF-16 `offset` in the line's
 * text (e.g. the word clicked) as a point when the map is exact. Null when the chunk does
 * not contain the line.
 */
export function textForLine (map: ChunkLayoutMap, pageId: string, lineId: string, offset?: number): TextHit | null {
  const pieces = map.pieces.filter(p => p.pageId === pageId && p.lineId === lineId)
  if (!pieces.length) return null
  const first = pieces[0]
  const last = pieces[pieces.length - 1]
  let point = first.start
  if (map.precision === 'exact' && offset !== undefined) {
    const piece = pieces.find(p => offset >= p.lineStart && offset < p.lineEnd) ?? (offset >= last.lineEnd ? last : first)
    point = piece.start + Math.max(0, Math.min(offset, piece.lineEnd) - piece.lineStart)
    point = Math.min(point, piece.end)
  }
  const holdsOffset = offset === undefined ? null : pieces.some(p => offset >= p.lineStart && offset < p.lineEnd)
  return { chunkId: map.chunkId, start: first.start, end: last.end, point, precision: map.precision, holdsOffset }
}

/** The part of a chunk's text on a page, `[start, end)`; null when none is. */
export function rangeOnPage (map: ChunkLayoutMap, pageId: string): { start: number, end: number } | null {
  const on = map.pieces.filter(p => p.pageId === pageId)
  if (!on.length) return null
  return { start: on[0].start, end: on[on.length - 1].end }
}

/** A place in a chunk's text where a page's text begins. */
export interface PageBreak {
  /** UTF-16 offset in the chunk: the first character from the new page. */
  offset: number
  pageId: string
  precision: Precision
}

/**
 * Where text from a new page begins in a chunk: at the first piece of the first line of a
 * page (the page files hold only lines of the text, so that line starts the page's text),
 * and where the chunk continues onto another page. A chunk starting in the middle of a page
 * gets no break at its start.
 */
export function pageBreaks (
  map: ChunkLayoutMap, firstLineOf: (pageId: string) => string | undefined, text?: string
): PageBreak[] {
  const out: PageBreak[] = []
  map.pieces.forEach((piece, i) => {
    const previous = map.pieces[i - 1]
    const newPage = previous ? previous.pageId !== piece.pageId : piece.lineStart === 0 && firstLineOf(piece.pageId) === piece.lineId
    if (!newPage) return
    // An approximate walk drifts: put its break at the nearest word start, not inside a word.
    const offset = map.precision === 'approximate' && text !== undefined && piece.start > 0 ? nearestWordStart(text, piece.start) : piece.start
    out.push({ offset, pageId: piece.pageId, precision: map.precision })
  })
  return out
}

const SNAP = 16
const space = (c: string | undefined) => c === undefined || /\s/u.test(c)

/** The start of a word (after whitespace) nearest to `offset`, within a few units; else `offset`. */
function nearestWordStart (text: string, offset: number): number {
  for (let d = 0; d <= SNAP; d++) {
    for (const i of [offset - d, offset + d]) {
      if (i > 0 && i < text.length && space(text[i - 1]) && !space(text[i])) return i
    }
  }
  return offset
}

/** The pages a chunk's text is on, in order. */
export function pagesOf (map: ChunkLayoutMap): string[] {
  const out: string[] = []
  for (const piece of map.pieces) if (out[out.length - 1] !== piece.pageId) out.push(piece.pageId)
  return out
}

/**
 * A text selection as a range anchored on its first chunk, `end` measured across the
 * following chunks (as annotation offsets are). A selection reaching past a gap in chunk
 * order ends at the gap. Null when a point is not in `chunks`.
 */
export function selectionRange (
  start: { chunkId: string, charOffset: number }, end: { chunkId: string, charOffset: number },
  chunks: readonly { id: string, order: number, text: string }[]
): { chunkId: string, start: number, end: number } | null {
  let a = chunks.findIndex(c => c.id === start.chunkId)
  let b = chunks.findIndex(c => c.id === end.chunkId)
  if (a < 0 || b < 0) return null
  let [from, to] = [start, end]
  if (b < a || (a === b && end.charOffset < start.charOffset)) {
    [a, b] = [b, a];
    [from, to] = [to, from]
  }
  let offset = 0
  for (let i = a; i < b; i++) {
    if (chunks[i + 1].order !== chunks[i].order + 1) return { chunkId: from.chunkId, start: from.charOffset, end: offset + (chunks[i].text ?? '').length }
    offset += (chunks[i].text ?? '').length
  }
  return { chunkId: from.chunkId, start: from.charOffset, end: offset + to.charOffset }
}
