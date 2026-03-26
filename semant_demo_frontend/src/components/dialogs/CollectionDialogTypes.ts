import { Collection } from 'src/models/collection'

type DialogType = 'CREATE' | 'EDIT'

interface CollectionDialogProps {
  dialogType: DialogType
  collection?: Collection
}

export type { DialogType, CollectionDialogProps }
