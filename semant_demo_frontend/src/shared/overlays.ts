// Quasar overlays still in the DOM on keydown; they close themselves on keyup.
const OPEN_OVERLAY = '.q-menu, .q-dialog, .q-drawer__backdrop:not(.hidden)'

/**
 * Whether a Quasar menu, dialog or overlay drawer is open, which handles Escape itself.
 * `inside`: an element in a dialog that handles Escape on its own; that dialog does not count.
 */
export function overlayOpen (doc: Document = document, inside?: Element): boolean {
  if (!inside) return doc.querySelector(OPEN_OVERLAY) !== null
  return Array.from(doc.querySelectorAll(OPEN_OVERLAY)).some((overlay) => !overlay.contains(inside))
}
