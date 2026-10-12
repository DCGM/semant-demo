import { useQuasar } from 'quasar'

import SpanDiscussionDialog from './SpanDiscussionDialog.vue'
import type { SpanDiscussionDialogProps } from './SpanDiscussionDialogTypes'

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
