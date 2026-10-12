import { useQuasar } from 'quasar'

import TagsDialog from './TagsDialog.vue'
import { TagsDialogProps } from './TagsDialogTypes'

const useTagsDialog = () => {
  const $q = useQuasar()

  const openTagsDialog = (props: TagsDialogProps) => {
    return $q.dialog({
      component: TagsDialog,
      componentProps: props
    })
  }

  return { openTagsDialog }
}

export default useTagsDialog
