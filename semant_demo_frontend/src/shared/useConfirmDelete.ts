import { useQuasar } from 'quasar'
import ConfirmDeleteDialog from './ui/ConfirmDeleteDialog.vue'

export interface ConfirmDeleteOptions {
  title: string
  message: string
  okLabel?: string
  /** What else would be deleted along, as text; empty when nothing. */
  alsoDeletes: () => Promise<string>
}

/** Opens the delete confirmation that says what else would be deleted along (#479). */
export default function useConfirmDelete () {
  const $q = useQuasar()
  return (options: ConfirmDeleteOptions) => $q.dialog({ component: ConfirmDeleteDialog, componentProps: options })
}
