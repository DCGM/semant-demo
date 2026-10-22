import { useQuasar } from 'quasar'
import ConfirmDeleteDialog from './ui/ConfirmDeleteDialog.vue'
import type { AnnotationCounter } from 'src/features/annotations/annotationCounts'

export interface ConfirmDeleteOptions {
  title: string
  message: string
  okLabel?: string
  count: AnnotationCounter
}

/** Opens the delete confirmation that counts the annotations deleted along (#479). */
export default function useConfirmDelete () {
  const $q = useQuasar()
  return (options: ConfirmDeleteOptions) => $q.dialog({ component: ConfirmDeleteDialog, componentProps: options })
}
