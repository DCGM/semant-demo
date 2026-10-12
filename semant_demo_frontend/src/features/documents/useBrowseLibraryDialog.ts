import { useQuasar } from 'quasar'
import BrowseLibraryDialog from './BrowseLibraryDialog.vue'
import { BrowseLibraryDialogProps } from './BrowseLibraryDialogTypes'

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
