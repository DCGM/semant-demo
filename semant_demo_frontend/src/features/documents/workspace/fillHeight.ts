/**
 * A QPage `style-fn` for the document views (#600): the page is exactly as tall as its
 * layout's room under the header (`offset`), instead of at least as tall, so the page does
 * not scroll and the panes inside it scroll on their own.
 */
export function fillHeight (offset: number, height: number): Record<string, string> {
  return { height: `${Math.max(0, height - offset)}px` }
}
