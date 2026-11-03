// The scan view's transform: viewer pixel = scan pixel × scale + (x, y). The image and its
// line overlay are drawn in scan pixels inside one transformed element, so they always share
// one coordinate system. Pure functions; the component owns the state.

import type { Point, Rect } from './pageLayout'

export interface Transform {
  scale: number
  x: number
  y: number
}

export interface Size {
  width: number
  height: number
}

export interface ScaleLimits {
  min: number
  max: number
}

/** Space left around a fitted page, in viewer pixels. */
export const FIT_PADDING = 12
/** Most image magnification: 4 viewer pixels per scan pixel. */
export const MAX_SCALE = 4
/** Factor of one zoom step (+/- keys and buttons). */
export const ZOOM_STEP = 1.25
/** Viewer pixels of the image that stay inside the viewer however far it is panned. */
export const KEEP_VISIBLE = 64

const valid = (s: Size) => s.width > 0 && s.height > 0

/** The whole page centered in the viewer. */
export function fitTransform (image: Size, viewer: Size, padding = FIT_PADDING): Transform {
  if (!valid(image) || !valid(viewer)) return { scale: 1, x: 0, y: 0 }
  const scale = Math.max(1e-3, Math.min((viewer.width - 2 * padding) / image.width, (viewer.height - 2 * padding) / image.height))
  return { scale, x: (viewer.width - image.width * scale) / 2, y: (viewer.height - image.height * scale) / 2 }
}

/** From half the fitted size to {@link MAX_SCALE} (or the fitted size, if larger). */
export function scaleLimits (image: Size, viewer: Size): ScaleLimits {
  const fit = fitTransform(image, viewer).scale
  return { min: fit / 2, max: Math.max(fit, MAX_SCALE) }
}

/** `t` moved so that at least {@link KEEP_VISIBLE} pixels of the image stay in view on each axis. */
export function clampTransform (t: Transform, image: Size, viewer: Size): Transform {
  const axis = (pos: number, extent: number, view: number) => {
    const keep = Math.min(KEEP_VISIBLE, extent / 2, view / 2)
    return Math.min(view - keep, Math.max(keep - extent, pos))
  }
  return { scale: t.scale, x: axis(t.x, image.width * t.scale, viewer.width), y: axis(t.y, image.height * t.scale, viewer.height) }
}

/** `t` scaled by `factor` about `anchor` (viewer pixels), which stays in place. */
export function zoomAt (t: Transform, factor: number, anchor: Point, limits: ScaleLimits): Transform {
  const scale = Math.min(limits.max, Math.max(limits.min, t.scale * factor))
  const k = scale / t.scale
  return { scale, x: anchor[0] - (anchor[0] - t.x) * k, y: anchor[1] - (anchor[1] - t.y) * k }
}

/** Where a two-finger gesture started: the transform, the fingers' midpoint and spread. */
export interface PinchStart {
  transform: Transform
  mid: Point
  distance: number
}

/**
 * The transform during a pinch: scaled by how far the fingers spread since `start`, with
 * the scan point first under their midpoint kept under the current midpoint, so the page
 * follows the fingers when they also move together.
 */
export function pinchTransform (start: PinchStart, mid: Point, distance: number, limits: ScaleLimits): Transform {
  const factor = start.distance > 0 ? distance / start.distance : 1
  const scale = Math.min(limits.max, Math.max(limits.min, start.transform.scale * factor))
  const [ax, ay] = toScan(start.transform, start.mid)
  return { scale, x: mid[0] - ax * scale, y: mid[1] - ay * scale }
}

export const toScan = (t: Transform, p: Point): Point => [(p[0] - t.x) / t.scale, (p[1] - t.y) / t.scale]
export const toViewer = (t: Transform, p: Point): Point => [p[0] * t.scale + t.x, p[1] * t.scale + t.y]

export function rectToViewer (t: Transform, r: Rect): Rect {
  return { x: r.x * t.scale + t.x, y: r.y * t.scale + t.y, width: r.width * t.scale, height: r.height * t.scale }
}

/**
 * The same scan point under the viewer's center before and after the viewer was resized from
 * `before` to `after`, so a zoomed-in page does not drift when the layout changes.
 */
export function keepCenter (t: Transform, before: Size, after: Size): Transform {
  const center = toScan(t, [before.width / 2, before.height / 2])
  return { scale: t.scale, x: after.width / 2 - center[0] * t.scale, y: after.height / 2 - center[1] * t.scale }
}

export interface FocusOptions {
  /** Viewer pixels a target keeps from the viewer's edges. */
  margin?: number
  /** A target (e.g. a text line) shown smaller than this many pixels high is too small to read. */
  minReadableHeight?: number
  /** The height an unreadably small target is zoomed to. */
  readableHeight?: number
  limits?: ScaleLimits
}

/**
 * Smart focus: the transform that makes `target` (scan pixels) visible, or null when it is
 * visible enough already. It pans only when the target is not fully inside the viewer with
 * `margin` to spare, by the least distance needed (a target larger than the viewer is
 * aligned at its top-left corner), and zooms in only when the target is shown smaller than
 * `minReadableHeight` (never out). Routine use, e.g. stepping through lines, therefore moves
 * the page only when a line leaves the view.
 */
export function smartFocus (t: Transform, target: Rect, viewer: Size, options: FocusOptions = {}): Transform | null {
  const margin = options.margin ?? 24
  const minReadable = options.minReadableHeight ?? 10
  const readable = options.readableHeight ?? 20
  const limits = options.limits ?? { min: 0, max: MAX_SCALE }
  if (!valid(viewer) || target.width < 0 || target.height < 0) return null

  let scale = t.scale
  if (target.height * scale < minReadable && target.height > 0) {
    // Zoom in to a readable height, but not so far that the target no longer fits across.
    const fitsAcross = target.width > 0 ? (viewer.width - 2 * margin) / target.width : Infinity
    scale = Math.min(limits.max, readable / target.height, Math.max(fitsAcross, scale))
    scale = Math.max(scale, t.scale)
  }
  let x = t.x
  let y = t.y
  if (scale !== t.scale) {
    // Zoom about the target's center, keeping it where it was on screen (clamped below).
    const cx = target.x + target.width / 2
    const cy = target.y + target.height / 2
    const [sx, sy] = toViewer(t, [cx, cy])
    x = sx - cx * scale
    y = sy - cy * scale
  }
  const shift = (start: number, extent: number, view: number) => {
    if (extent > view - 2 * margin) return margin - start
    if (start < margin) return margin - start
    if (start + extent > view - margin) return view - margin - (start + extent)
    return 0
  }
  const dx = shift(target.x * scale + x, target.width * scale, viewer.width)
  const dy = shift(target.y * scale + y, target.height * scale, viewer.height)
  if (scale === t.scale && Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return null
  return { scale, x: x + dx, y: y + dy }
}
