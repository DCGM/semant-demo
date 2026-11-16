/**
 * Scrolling a KWIC row into view below whatever covers the top of the page (#704): the fixed
 * app header, and any sticky header that is stuck there (e.g. a sticky column header or toolbar
 * added later). The cover is measured when scrolling, so a taller or wrapped header, or one that
 * is added, is accounted for without a fixed margin in CSS.
 */

/** Elements that may cover the top of the page while the list scrolls under them. */
const COVER_SELECTOR = '.q-header, [data-covers-top]'

/** Space kept between the cover and the row. */
const GAP = 8

/**
 * How far from the top of the viewport the page is covered: fixed or sticky elements in
 * `COVER_SELECTOR` that start at the top of the viewport or right below a cover there (a toolbar
 * stuck below the app header), down to the lowest bottom edge among them.
 */
export function topCover (doc: Document = document): number {
  const rects = Array.from(doc.querySelectorAll<HTMLElement>(COVER_SELECTOR))
    .filter(el => ['fixed', 'sticky'].includes(getComputedStyle(el).position))
    .map(el => el.getBoundingClientRect())
    .filter(rect => rect.height > 0)
    .sort((a, b) => a.top - b.top)
  let cover = 0
  // A sticky header further down the page covers nothing yet.
  for (const rect of rects) if (rect.top <= cover + 1) cover = Math.max(cover, rect.bottom)
  return cover
}

/**
 * Scrolls `row` into view minimally and only vertically (a list scrolled sideways keeps its
 * scroll, the row is wider), clear of the covered top of the page. Focus is not changed.
 */
export function scrollRowIntoView (row: HTMLElement, behavior: ScrollBehavior = 'auto'): void {
  row.style.scrollMarginTop = `${Math.ceil(topCover(row.ownerDocument)) + GAP}px`
  row.scrollIntoView?.({ block: 'nearest', inline: 'nearest', behavior })
}
