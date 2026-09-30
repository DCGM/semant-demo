import { useQuasar } from 'quasar'

import SpanDiscussionDialog from 'src/components/dialogs/SpanDiscussionDialog.vue'
import type { SpanDiscussionDialogProps } from 'src/components/dialogs/SpanDiscussionDialogTypes'

const useSpanDiscussionDialog = () => {
  const $q = useQuasar()

  const openSpanDiscussionDialog = (props: SpanDiscussionDialogProps) =>
    $q.dialog({
      component: SpanDiscussionDialog,
      componentProps: props
    })

  return { openSpanDiscussionDialog }
}

export default useSpanDiscussionDialog
