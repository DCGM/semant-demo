/**
 * Below this card width (px) a Search result previews its passage (about six lines, with
 * Show full text). A desktop window with both sidebars open (280 + 420 px) falls below it
 * up to roughly 1440 px wide; phones always do.
 */
export const CONSTRAINED_RESULT_WIDTH = 720

export function isConstrainedResultWidth (width: number): boolean {
  return width > 0 && width < CONSTRAINED_RESULT_WIDTH
}

const EDITABLE = 'input, textarea, select, [contenteditable=""], [contenteditable="true"], [role="combobox"], [role="listbox"], [role="menu"], [role="dialog"]'
// Quasar overlays still in the DOM on keydown; they close themselves on keyup.
const OPEN_OVERLAY = '.q-menu, .q-dialog, .q-drawer__backdrop:not(.hidden)'

/**
 * Whether an Escape keydown should clear the Search selection: not when a field, menu,
 * dialog or overlay drawer needs Escape for itself.
 */
export function escapeClearsSelection (event: KeyboardEvent, doc: Document = document): boolean {
  if (event.key !== 'Escape' || event.defaultPrevented) return false
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || event.isComposing) return false
  const target = event.target
  if (target instanceof Element && target.closest(EDITABLE)) return false
  return doc.querySelector(OPEN_OVERLAY) === null
}
