/** A span's marker in the annotation gutter, positioned next to the text it covers. */
export interface SpanMarker {
  spanId: string
  chunkId: string
  tagId: string
  start: number
  end: number
  /** Pixels from the top of the reader card. */
  top: number
  height: number
  column: number
  isAuto: boolean
}
