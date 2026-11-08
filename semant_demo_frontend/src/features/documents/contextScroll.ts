/**
 * Scrolling a document passage to its target so that the motion shows where the target
 * lies relative to the previous one (#493): earlier text scrolls up, later text down.
 */

/** Where the target is put before the smooth scroll, in viewport heights from the centre. */
const LEAD = 0.75

/**
 * How far to jump (instantly, in px, positive = down) before smooth-scrolling to the
 * target, or 0 to smooth-scroll from where the passage is. `offset` is the distance of
 * the target's centre from the viewport's centre (positive = below), `viewport` the
 * scroller's height and `direction` the target's place relative to the previous target
 * (1 later, -1 earlier, 0 the same or unknown).
 *
 * A target more than a viewport away is brought to {@link LEAD} of a viewport from the
 * centre, so the smooth scroll never races through the text in between; one clearly on
 * the wrong side is brought to the side it lies on, so the motion goes the right way.
 *
 * `replaced`: the passage was replaced since the previous target, so the old position
 * means nothing. The target is then brought in from its side unless it already lies a
 * clear distance (a quarter of a viewport) on that side.
 */
export function leadJump (offset: number, viewport: number, direction: -1 | 0 | 1, replaced = false): number {
  if (!direction || viewport <= 0) return 0
  const along = offset * direction
  const nearest = replaced ? viewport / 4 : -viewport / 4
  if (along <= viewport && along >= nearest) return 0
  return offset - direction * LEAD * viewport
}

/** The nearest ancestor of `el` that scrolls vertically, or the page's scroller. */
export function scrollerOf (el: HTMLElement): HTMLElement {
  for (let node = el.parentElement; node; node = node.parentElement) {
    const overflow = getComputedStyle(node).overflowY
    if ((overflow === 'auto' || overflow === 'scroll') && node.scrollHeight > node.clientHeight) return node
  }
  return (document.scrollingElement as HTMLElement | null) ?? document.documentElement
}

/** Whether the user asked for less motion (no smooth scrolling). */
export function prefersReducedMotion (): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * Scrolls `el` into view (its start when `tall`, otherwise its centre), first jumping as
 * {@link leadJump} says so the motion goes in `direction` (`replaced`: the passage was
 * replaced since the previous target). `topInset` is the height covered by a sticky header
 * at the top of the scroller.
 */
export function scrollToTarget (el: HTMLElement, direction: -1 | 0 | 1, tall: boolean, topInset = 0, replaced = false) {
  const behavior: ScrollBehavior = prefersReducedMotion() ? 'auto' : 'smooth'
  const scroller = scrollerOf(el)
  const page = scroller === document.scrollingElement || scroller === document.documentElement
  const top = page ? 0 : scroller.getBoundingClientRect().top
  const viewport = page ? window.innerHeight : scroller.clientHeight
  const rect = el.getBoundingClientRect()
  const visible = viewport - topInset
  const offset = (rect.top - top - topInset) + (tall ? 0 : rect.height / 2) - (tall ? 0 : visible / 2)
  const jump = behavior === 'smooth' ? leadJump(offset, visible, direction, replaced) : 0
  if (jump) scroller.scrollBy?.({ top: jump, behavior: 'instant' as ScrollBehavior })
  el.scrollIntoView?.({ behavior, block: tall ? 'start' : 'center' })
}
