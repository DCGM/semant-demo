import { useQuasar } from 'quasar'
import BrowseLibraryDialog from 'src/components/dialogs/BrowseLibraryDialog.vue'
import { BrowseLibraryDialogProps } from 'src/components/dialogs/BrowseLibraryDialogTypes'

const useBrowseLibraryDialog = () => {
  const $q = useQuasar()

  const openBrowseLibraryDialog = (props: BrowseLibraryDialogProps) => {
    return $q.dialog({
      component: BrowseLibraryDialog,
      componentProps: props
    })
  }

  return { openBrowseLibraryDialog }
}

export default useBrowseLibraryDialog
