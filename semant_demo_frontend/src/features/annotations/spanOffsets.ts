/**
 * Span coordinates, the frontend twin of semant_demo/features/annotations/offsets.py.
 *
 * A span is anchored on the chunk where it starts; `start`/`end` are half-open offsets
 * in UTF-16 code units (`String.length`) from the start of that chunk's text. `end` may
 * exceed the anchor's length: the span then continues into the following chunks of the
 * document while their `order` values are consecutive. Shared cases:
 * semant_demo_backend/tests/fixtures/text_offsets.json.
 */

export interface OrderedText {
  order: number
  text: string
}

export interface ChunkPart {
  chunk: number
  start: number
  end: number
}

/**
 * Offset from the start of `chunks[fromIndex]` to the start of `chunks[toIndex]`, or
 * null if `toIndex` comes first or a gap in `order` lies between them.
 */
export function offsetBetween (chunks: OrderedText[], fromIndex: number, toIndex: number): number | null {
  if (toIndex < fromIndex) return null
  let offset = 0
  for (let i = fromIndex; i < toIndex; i++) {
    if (chunks[i + 1].order !== chunks[i].order + 1) return null
    offset += chunks[i].text.length
  }
  return offset
}

/** `[start, end)` clipped to a chunk of `length` that starts at `offset`, or null if empty. */
export function localRange (start: number, end: number, offset: number, length: number): { start: number, end: number } | null {
  const localStart = Math.max(0, start - offset)
  const localEnd = Math.min(length, end - offset)
  return localEnd > localStart ? { start: localStart, end: localEnd } : null
}

/** The parts of a span anchored on `chunks[anchor]` in each chunk it covers. */
export function projectSpan (chunks: OrderedText[], anchor: number, start: number, end: number): ChunkPart[] {
  const parts: ChunkPart[] = []
  for (let i = anchor; i < chunks.length; i++) {
    const offset = offsetBetween(chunks, anchor, i)
    if (offset === null) break
    const range = localRange(start, end, offset, chunks[i].text.length)
    if (range) parts.push({ chunk: i, ...range })
  }
  return parts
}

/**
 * The same range anchored on the chunk where it starts, as spans are stored: `start`/`end`
 * count from `chunks[index]` and may lie before or after it (an edited boundary). The anchor
 * moves only across consecutive `order` values; null when the start is outside the reachable
 * chunks or the range is empty.
 */
export function anchorAtStart (chunks: OrderedText[], index: number, start: number, end: number):
  { index: number, start: number, end: number } | null {
  // Forward while the start is past this chunk, backward while it is before it.
  while (index < chunks.length - 1 && start >= chunks[index].text.length) {
    if (chunks[index + 1].order !== chunks[index].order + 1) break
    start -= chunks[index].text.length
    end -= chunks[index].text.length
    index += 1
  }
  while (index > 0 && start < 0) {
    if (chunks[index].order !== chunks[index - 1].order + 1) break
    index -= 1
    start += chunks[index].text.length
    end += chunks[index].text.length
  }
  if (start < 0 || start >= chunks[index].text.length || end <= start) return null
  return { index, start, end }
}
