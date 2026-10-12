import { useQuasar } from 'quasar'
import CollectionDialog from './CollectionDialog.vue'
import { CollectionDialogProps } from './CollectionDialogTypes'

const useCollectionDialog = () => {
  const $q = useQuasar()

  const openCollectionDialog = (props: CollectionDialogProps) => {
    return $q.dialog({
      component: CollectionDialog,
      componentProps: props
    })
  }

  return { openCollectionDialog }
}

export default useCollectionDialog
