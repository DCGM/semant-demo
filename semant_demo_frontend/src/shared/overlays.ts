// Quasar overlays still in the DOM on keydown; they close themselves on keyup.
const OPEN_OVERLAY = '.q-menu, .q-dialog, .q-drawer__backdrop:not(.hidden)'

/**
 * Whether a Quasar menu, dialog or overlay drawer is open, which handles Escape itself.
 * `inside`: an element in a dialog that handles Escape on its own. That dialog does not
 * count, nor do overlay drawers, which lie under it and do not get its Escape.
 */
export function overlayOpen (doc: Document = document, inside?: Element): boolean {
  if (!inside) return doc.querySelector(OPEN_OVERLAY) !== null
  return Array.from(doc.querySelectorAll('.q-menu, .q-dialog')).some((overlay) => !overlay.contains(inside))
}
