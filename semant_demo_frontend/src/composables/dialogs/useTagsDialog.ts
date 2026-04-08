import { useQuasar } from 'quasar'

import TagsDialog from 'src/components/dialogs/TagsDialog.vue'
import { TagsDialogProps } from 'src/components/dialogs/TagsDialogTypes'

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
