import { Tag } from 'src/models/tags'

type DialogType = 'CREATE' | 'EDIT'

interface TagsDialogProps {
  dialogType: DialogType
  tag?: Tag
}

export type { DialogType, TagsDialogProps }
