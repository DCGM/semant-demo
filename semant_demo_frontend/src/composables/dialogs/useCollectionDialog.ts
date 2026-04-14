import { useQuasar } from 'quasar'
import CollectionDialog from 'src/components/dialogs/CollectionDialog.vue'
import { CollectionDialogProps } from 'src/components/dialogs/CollectionDialogTypes'

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
