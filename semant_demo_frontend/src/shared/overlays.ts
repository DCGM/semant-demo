// Quasar overlays still in the DOM on keydown; they close themselves on keyup.
const OPEN_OVERLAY = '.q-menu, .q-dialog, .q-drawer__backdrop:not(.hidden)'

/** Whether a Quasar menu, dialog or overlay drawer is open, which handles Escape itself. */
export function overlayOpen (doc: Document = document): boolean {
  return doc.querySelector(OPEN_OVERLAY) !== null
}
