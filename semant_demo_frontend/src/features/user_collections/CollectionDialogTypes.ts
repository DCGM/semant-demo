import { Collection } from 'src/generated/api'

type DialogType = 'CREATE' | 'EDIT'

interface CollectionDialogProps {
  dialogType: DialogType
  collection?: Collection
}

export type { DialogType, CollectionDialogProps }
