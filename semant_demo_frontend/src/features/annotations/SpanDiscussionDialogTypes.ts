export interface SpanDiscussionDialogProps {
  /** The collection the span belongs to (its annotation scope). */
  collectionId: string
  spanId: string
  spanText?: string
  tagName?: string
  tagColor?: string
}
