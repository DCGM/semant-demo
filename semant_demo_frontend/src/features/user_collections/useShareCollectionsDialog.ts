import { useQuasar } from 'quasar'
import ShareCollectionsDialog from './ShareCollectionsDialog.vue'
import { ShareCollectionsDialogProps } from './ShareCollectionsDialogTypes'

const useShareCollectionsDialog = () => {
  const $q = useQuasar()

  const openShareCollectionsDialog = (props: ShareCollectionsDialogProps) => {
    return $q.dialog({
      component: ShareCollectionsDialog,
      componentProps: props
    })
  }

  return { openShareCollectionsDialog }
}

export default useShareCollectionsDialog
