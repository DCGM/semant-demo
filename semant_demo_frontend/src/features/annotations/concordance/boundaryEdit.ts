import type { DocumentChunk } from 'src/generated/api'
import { anchorAtStart, offsetBetween, type OrderedText } from '../spanOffsets'

/**
 * Boundary editing of an annotation in the workspace's source passage (#461), with the
 * coordinates of the document view (`spanOffsets.ts`): a range is anchored on the chunk
 * where it starts, so moving the start into another chunk moves the annotation there (#436).
 * Boundaries move within the loaded chunks of consecutive `order` around the anchor.
 */

/** A range as spans store it: offsets counted from the chunk where it starts. */
export interface BoundaryRange {
  chunkId: string
  start: number
  end: number
}

export type BoundaryHandle = 'start' | 'end'
export type BoundaryUnit = 'word' | 'character'

/** A point in the loaded text: an offset in a chunk's text. */
export interface TextPoint {
  chunkId: string
  offset: number
}

/** Chunks without an order are gaps: nothing continues into or out of them. */
const ordered = (chunks: readonly DocumentChunk[]): OrderedText[] =>
  chunks.map(c => ({ order: c.order ?? Number.NaN, text: c.text }))

/** The loaded chunks of consecutive order around `index`, and their joined text. */
function runAround (loaded: readonly DocumentChunk[], index: number) {
  const chunks = ordered(loaded)
  let first = index
  while (first > 0 && offsetBetween(chunks, first - 1, first) !== null) first--
  let last = index
  while (last < chunks.length - 1 && offsetBetween(chunks, last, last + 1) !== null) last++
  const text = chunks.slice(first, last + 1).map(c => c.text).join('')
  /** Offset of `chunks[i]` (in the run) in the joined text. */
  const base = (i: number) => offsetBetween(chunks, first, i) ?? 0
  return { first, last, text, base }
}

const isSpace = (c: string | undefined) => c !== undefined && /\s/.test(c)

/** A code point never splits: a step over a surrogate pair takes both halves. */
function charStep (text: string, at: number, direction: -1 | 1): number {
  if (direction > 0) {
    const code = text.charCodeAt(at)
    return at + (code >= 0xd800 && code <= 0xdbff && at + 1 < text.length ? 2 : 1)
  }
  const code = text.charCodeAt(at - 1)
  return at - (code >= 0xdc00 && code <= 0xdfff && at >= 2 ? 2 : 1)
}

/** The next word boundary from `at`: a start moves to word starts, an end to word ends. */
function wordStep (text: string, at: number, handle: BoundaryHandle, direction: -1 | 1): number {
  let i = at
  if (direction < 0) {
    if (handle === 'start') {
      while (i > 0 && isSpace(text[i - 1])) i--
      while (i > 0 && !isSpace(text[i - 1])) i--
    } else {
      while (i > 0 && !isSpace(text[i - 1])) i--
      while (i > 0 && isSpace(text[i - 1])) i--
    }
  } else if (handle === 'start') {
    while (i < text.length && !isSpace(text[i])) i++
    while (i < text.length && isSpace(text[i])) i++
  } else {
    while (i < text.length && isSpace(text[i])) i++
    while (i < text.length && !isSpace(text[i])) i++
  }
  return i
}

/** `[start, end)` of the run's joined text anchored where it starts, or null. */
function anchored (chunks: readonly DocumentChunk[], first: number, start: number, end: number): BoundaryRange | null {
  const range = anchorAtStart(ordered(chunks), first, start, end)
  return range ? { chunkId: chunks[range.index].id, start: range.start, end: range.end } : null
}

/**
 * Moves one boundary of `range` by a word or a character; null when it cannot move that way
 * (the start must stay before the end, both within the loaded text). The other boundary is
 * never changed, also when it lies past the loaded text.
 */
export function stepBoundary (chunks: readonly DocumentChunk[], range: BoundaryRange, handle: BoundaryHandle,
  direction: -1 | 1, unit: BoundaryUnit): BoundaryRange | null {
  const index = chunks.findIndex(c => c.id === range.chunkId)
  if (index < 0) return null
  const run = runAround(chunks, index)
  const offset = run.base(index)
  let start = offset + range.start
  // The end may lie past the loaded text (the annotation continues into chunks not shown):
  // a start step keeps it as it is; the end itself moves only once its text is shown.
  let end = offset + range.end
  if (handle === 'end' && end > run.text.length) return null
  const from = handle === 'start' ? start : end
  const to = unit === 'word' ? wordStep(run.text, from, handle, direction) : charStep(run.text, from, direction)
  if (to === from || to < 0 || to > run.text.length) return null
  if (handle === 'start') start = to
  else end = to
  if (start >= end) return null
  return anchored(chunks, run.first, start, end)
}

/** The range between two points of the loaded text (in either order), or null when they
 * are not in consecutive chunks or select nothing. */
export function rangeBetween (chunks: readonly DocumentChunk[], a: TextPoint, b: TextPoint): BoundaryRange | null {
  const ia = chunks.findIndex(c => c.id === a.chunkId)
  const ib = chunks.findIndex(c => c.id === b.chunkId)
  if (ia < 0 || ib < 0) return null
  const run = runAround(chunks, ia)
  if (ib < run.first || ib > run.last) return null
  const pa = run.base(ia) + a.offset
  const pb = run.base(ib) + b.offset
  return anchored(chunks, run.first, Math.min(pa, pb), Math.max(pa, pb))
}

/** The text of `range` in the loaded chunks (cut where the loaded text ends). */
export function rangeText (chunks: readonly DocumentChunk[], range: BoundaryRange): string {
  const index = chunks.findIndex(c => c.id === range.chunkId)
  if (index < 0) return ''
  const run = runAround(chunks, index)
  const offset = run.base(index)
  return run.text.slice(offset + range.start, offset + range.end)
}

export function sameRange (a: BoundaryRange, b: BoundaryRange): boolean {
  return a.chunkId === b.chunkId && a.start === b.start && a.end === b.end
}
