import { PostTag, Tag } from 'src/generated/api'

interface TagsDialogProps {
  /** The tag to edit; none: a new one. */
  tag?: Tag
  collectionId: string
  /** Creates the tag (`existing` null) or saves the fields of `existing`, answering with the tag
   * as saved; the dialog stays open, showing the message, when it throws. */
  save: (payload: PostTag, existing: Tag | null) => Promise<Tag>
}

export type { TagsDialogProps }
