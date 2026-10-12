import { Tag } from 'src/generated/api'

type DialogType = 'CREATE' | 'EDIT'

interface TagsDialogProps {
  dialogType: DialogType
  tag?: Tag
}

export type { DialogType, TagsDialogProps }
