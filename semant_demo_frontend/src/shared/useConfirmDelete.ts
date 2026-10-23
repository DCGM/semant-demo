import { useQuasar } from 'quasar'
import ConfirmDeleteDialog from './ui/ConfirmDeleteDialog.vue'
import type { ConfirmDeleteOptions } from './ui/ConfirmDeleteDialogTypes'

/** Opens the delete confirmation that says what else would be deleted along (#479). */
export default function useConfirmDelete () {
  const $q = useQuasar()
  return (options: ConfirmDeleteOptions) => $q.dialog({ component: ConfirmDeleteDialog, componentProps: options })
}
