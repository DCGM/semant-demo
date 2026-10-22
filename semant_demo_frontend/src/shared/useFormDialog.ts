import { onBeforeUnmount, watch, type ComponentPublicInstance, type Ref } from 'vue'
import { useQuasar } from 'quasar'
import { overlayOpen } from './overlays'

// Quasar's clear (✕) and other in-field actions; Tab should go from field to field (#479).
const FIELD_ACTION = '.q-field__focusable-action'

/**
 * Keyboard behaviour shared by the create/edit form dialogs (#479):
 * - `requestClose` closes at once when nothing was changed and otherwise asks before
 *   discarding, like Cancel;
 * - `onKeydown` and `onKeyup` (on the q-dialog) make Escape do the same, unless it closes
 *   an open menu (e.g. a select's options) instead;
 * - the fields' clear buttons are taken out of the Tab order (they appear and disappear
 *   with the field's value, so they are watched).
 */
export function useFormDialog (
  cardRef: Ref<ComponentPublicInstance | null>,
  isDirty: Ref<boolean>,
  close: () => void
) {
  const $q = useQuasar()

  const requestClose = () => {
    if (!isDirty.value) {
      close()
      return
    }
    $q.dialog({
      title: 'Unsaved Changes',
      message: 'You have unsaved changes. Are you sure you want to discard them?',
      ok: 'Yes',
      cancel: 'No',
      noBackdropDismiss: true
    }).onOk(close)
  }

  // Decided on keydown, while a menu that takes the Escape is still open, but acted on after
  // the keyup: Quasar closes the topmost dialog on that keyup (in a window listener), which
  // would otherwise be the question opened here.
  let escapePressed = false
  const onKeydown = (e: KeyboardEvent) => {
    if (e.key !== 'Escape') return
    const card = cardRef.value?.$el as Element | undefined
    escapePressed = !e.defaultPrevented && !e.isComposing && !overlayOpen(document, card)
    if (escapePressed) e.preventDefault()
  }
  const onKeyup = (e: KeyboardEvent) => {
    if (e.key !== 'Escape' || !escapePressed) return
    escapePressed = false
    setTimeout(requestClose)
  }

  const skipFieldActions = (root: Element) => {
    root.querySelectorAll(FIELD_ACTION).forEach((el) => el.setAttribute('tabindex', '-1'))
  }
  let observer: MutationObserver | null = null
  watch(() => cardRef.value?.$el as Element | undefined, (root) => {
    observer?.disconnect()
    observer = null
    if (!(root instanceof Element)) return
    skipFieldActions(root)
    observer = new MutationObserver(() => skipFieldActions(root))
    observer.observe(root, { childList: true, subtree: true })
  }, { immediate: true, flush: 'post' })
  onBeforeUnmount(() => observer?.disconnect())

  return { requestClose, onKeydown, onKeyup }
}
