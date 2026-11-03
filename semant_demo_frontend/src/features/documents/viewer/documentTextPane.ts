import type { Tag } from 'src/generated/api'
import type { LocalSelection, ProjectedSpan } from 'src/features/annotations/useAnnotations'
import type { ChunkRange, TextPoint } from './readerOffsets'

export type { ChunkRange, TextChunk, TextPoint } from './readerOffsets'

/**
 * What DocumentTextPane shows of a collection's annotations. Without it the pane is
 * read-only: plain text, native selection and copying, no spans or selection handles.
 * The pane only displays these; loading and editing them stays with its owner.
 */
export interface TextPaneAnnotation {
  tags: Tag[]
  /** The spans shown in a chunk. Return the same array while they are unchanged. */
  spansFor: (chunkId: string) => ProjectedSpan[]
  /** The part of the annotation selection in a chunk, with its drag handles. */
  selectionFor: (chunkId: string) => LocalSelection | null
  highlightSpanId?: string | null
  focusTagId?: string | null
}

/** Classes for a chunk's element, as in a `:class` binding. */
export type ChunkClass<T> = (chunk: T) => unknown

/** A non-empty text selection, its endpoints in document order. */
export interface TextSelection {
  start: TextPoint
  end: TextPoint
}

/** What the text shows of the scan pages (#544): the chunk's part on the page shown, page starts. */
export interface ChunkPageMarks {
  range?: { start: number, end: number } | null
  breaks: { offset: number, pageId: string, label: string, approximate?: boolean }[]
}

/** What a DocumentTextPane template ref offers its owner. */
export interface DocumentTextPaneApi {
  /** The text element: each chunk inside it is an element with `data-chunk-id`. */
  readonly root: HTMLElement | null
  /** Scrolls a chunk to the middle of the view. */
  scrollToChunk: (chunkId: string) => void
  /** Scrolls the start of a range to the middle of the view. */
  scrollToRange: (range: ChunkRange) => void
  /** Scrolls only when the start of the range is not visible enough; whether it scrolled. */
  revealRange: (range: Pick<ChunkRange, 'chunkId' | 'start'>, options?: { margin?: number }) => boolean
}
