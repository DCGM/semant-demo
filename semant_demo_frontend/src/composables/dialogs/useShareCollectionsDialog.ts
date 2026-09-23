import { useQuasar } from 'quasar'
import ShareCollectionsDialog from 'src/components/dialogs/ShareCollectionsDialog.vue'
import { ShareCollectionsDialogProps } from 'src/components/dialogs/ShareCollectionsDialogTypes'

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
