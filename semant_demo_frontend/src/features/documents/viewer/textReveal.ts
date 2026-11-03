// Smart focus in the text (#544): move the text only when a target is not visible enough.

export interface Band {
  top: number
  bottom: number
}

/**
 * How far to scroll (positive: down) so that `target` is visible in `view` with `margin`
 * (at most a quarter of the view) above and below it: 0 when it is already; to the middle
 * of the view when it is entirely out of view; else by the least distance, never pushing its
 * top above the margin.
 */
export function revealDelta (target: Band, view: Band, margin = 48): number {
  const height = view.bottom - view.top
  if (height <= 0) return 0
  const m = Math.max(0, Math.min(margin, height / 4))
  const top = view.top + m
  const bottom = view.bottom - m
  if (target.top >= top && target.bottom <= bottom) return 0
  if (target.bottom <= view.top || target.top >= view.bottom) {
    return Math.round((target.top + target.bottom) / 2 - (view.top + view.bottom) / 2)
  }
  if (target.top < top) return Math.round(target.top - top)
  return Math.round(Math.min(target.bottom - bottom, target.top - top))
}

/** The nearest ancestor of `el` that scrolls vertically, else the page. */
export function scrollContainer (el: HTMLElement): HTMLElement | null {
  for (let p = el.parentElement; p; p = p.parentElement) {
    const overflow = getComputedStyle(p).overflowY
    if ((overflow === 'auto' || overflow === 'scroll') && p.scrollHeight > p.clientHeight) return p
  }
  return (document.scrollingElement as HTMLElement | null) ?? null
}
