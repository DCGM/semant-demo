// Page layout files (`semant.page-layout` version 1, docs/PAGE_LAYOUT.md) as scan lines:
// each OCR line's baseline, the band around it from the heights above/below the baseline,
// and its approximate word starts. All geometry is in pixels of the served scan (`image`
// is its size), the coordinate system of the image and its overlay. Word positions are estimates
// (proportional to character positions); a line without them is used as a whole.

export type Point = readonly [number, number]

export interface Rect {
  x: number
  y: number
  width: number
  height: number
}

export interface ScanLine {
  /** Source line id from the PAGE XML, unique within the page. */
  id: string
  regionId: string
  /** Index of the line's region in the file (region ids need not be unique). */
  regionIndex: number
  /** Index in the page's serialization order. */
  index: number
  text: string
  baseline: Point[]
  /** Distance along the baseline at each baseline point (first 0, last `length`). */
  distances: number[]
  length: number
  /** Heights above and below the baseline; estimated when the file has none. */
  above: number
  below: number
  /** The band around the baseline: the upper edge left to right, then the lower edge back. */
  polygon: Point[]
  bounds: Rect
  /** Approximate word starts: distance along the baseline and UTF-16 offset in `text`.
   * Null when the file has none or they do not match the words of the text. */
  words: { distance: number, offset: number }[] | null
}

export interface PageLayout {
  pageId: string
  /** The scan size the geometry refers to, when the file states it. */
  image: { width: number, height: number } | null
  lines: ScanLine[]
  /** Lines left out because they are malformed or repeat an id. */
  skippedLines: number
}

export class LayoutFormatError extends Error {}

/** A word: a maximal run of letters, marks, digits and format characters (#463, as `word_spans`). */
const WORD = /[\p{L}\p{M}\p{N}\p{Cf}]+/gu

/** The UTF-16 offset where each word of `text` starts. */
export function wordOffsets (text: string): number[] {
  return Array.from(text.matchAll(WORD), m => m.index ?? 0)
}

const isNumber = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const isPoint = (v: unknown): v is [number, number] => Array.isArray(v) && v.length === 2 && isNumber(v[0]) && isNumber(v[1])

/** Heights of a line without its own: the page's median, else a share of the scan height. */
function fallbackHeights (heights: ([number, number] | null)[], imageHeight: number | null): [number, number] {
  const known = heights.filter((h): h is [number, number] => h !== null).sort((a, b) => (a[0] + a[1]) - (b[0] + b[1]))
  if (known.length) return known[Math.floor(known.length / 2)]
  const total = Math.max(8, (imageHeight ?? 2000) * 0.012)
  return [total * 0.75, total * 0.25]
}

function cumulative (points: Point[]): number[] {
  const out = [0]
  for (let i = 1; i < points.length; i++) {
    out.push(out[i - 1] + Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]))
  }
  return out
}

/** Unit normal pointing "up" from the text (towards smaller y for a left-to-right baseline). */
function normalAt (points: Point[], i: number): Point {
  const a = points[Math.max(0, i - 1)]
  const b = points[Math.min(points.length - 1, i + 1)]
  let dx = b[0] - a[0]
  let dy = b[1] - a[1]
  const len = Math.hypot(dx, dy)
  if (len === 0) return [0, -1]
  dx /= len
  dy /= len
  return [dy, -dx]
}

/** The band of the baseline points `points` between `above` and `below`. */
function band (points: Point[], above: number, below: number): Point[] {
  const upper: Point[] = []
  const lower: Point[] = []
  points.forEach((p, i) => {
    const [nx, ny] = normalAt(points, i)
    upper.push([p[0] + nx * above, p[1] + ny * above])
    lower.push([p[0] - nx * below, p[1] - ny * below])
  })
  return [...upper, ...lower.reverse()]
}

function boundsOf (points: readonly Point[]): Rect {
  const xs = points.map(p => p[0])
  const ys = points.map(p => p[1])
  const x = Math.min(...xs)
  const y = Math.min(...ys)
  return { x, y, width: Math.max(...xs) - x, height: Math.max(...ys) - y }
}

/**
 * Parse a page layout file. Throws {@link LayoutFormatError} when it is not a version 1
 * file of `pageId`; lines without a usable baseline or with a repeated id are left out.
 */
export function parsePageLayout (raw: unknown, pageId: string): PageLayout {
  const file = raw as Record<string, unknown> | null
  if (!file || typeof file !== 'object' || file.schema !== 'semant.page-layout' || file.version !== 1) {
    throw new LayoutFormatError('Not a page layout file of a supported version')
  }
  if (file.pageId !== pageId) throw new LayoutFormatError('The layout file belongs to another page')
  const img = file.image as Record<string, unknown> | null | undefined
  const image = img && isNumber(img.width) && isNumber(img.height) && img.width > 0 && img.height > 0
    ? { width: img.width, height: img.height }
    : null
  const regions = Array.isArray(file.regions) ? file.regions as Record<string, unknown>[] : []

  type Raw = { id: string, regionId: string, regionIndex: number, text: string, baseline: Point[], heights: [number, number] | null, wordStarts: unknown }
  const raws: Raw[] = []
  const seen = new Set<string>()
  let skipped = 0
  for (const [regionIndex, region] of regions.entries()) {
    const lines = Array.isArray(region?.lines) ? region.lines as Record<string, unknown>[] : []
    for (const line of lines) {
      const baseline = Array.isArray(line?.baseline) ? line.baseline : []
      if (typeof line?.id !== 'string' || !line.id || seen.has(line.id) || typeof line.text !== 'string' ||
          baseline.length < 1 || !baseline.every(isPoint)) {
        skipped++
        continue
      }
      seen.add(line.id)
      const h = line.heights
      const heights = Array.isArray(h) && h.length === 2 && isNumber(h[0]) && isNumber(h[1]) && h[0] >= 0 && h[1] >= 0
        ? [h[0], h[1]] as [number, number]
        : null
      // A one-point baseline is a line of zero length; keep it as a point.
      const points: Point[] = baseline.length === 1 ? [baseline[0], baseline[0]] : baseline
      raws.push({ id: line.id, regionId: String(region?.id ?? ''), regionIndex, text: line.text, baseline: points, heights, wordStarts: line.wordStarts })
    }
  }
  const fallback = fallbackHeights(raws.map(r => r.heights), image?.height ?? null)
  const lines = raws.map((r, index): ScanLine => {
    const [above, below] = r.heights ?? fallback
    const distances = cumulative(r.baseline)
    const length = distances[distances.length - 1]
    const polygon = band(r.baseline, Math.max(above, 1), Math.max(below, 1))
    return {
      id: r.id,
      regionId: r.regionId,
      regionIndex: r.regionIndex,
      index,
      text: r.text,
      baseline: r.baseline,
      distances,
      length,
      above,
      below,
      polygon,
      bounds: boundsOf(polygon),
      words: lineWords(r.text, r.wordStarts)
    }
  })
  return { pageId, image, lines, skippedLines: skipped }
}

function lineWords (text: string, starts: unknown): ScanLine['words'] {
  if (!Array.isArray(starts) || !starts.every(isNumber)) return null
  const offsets = wordOffsets(text)
  // Another word rule (e.g. a different Unicode version) would misplace every word.
  if (offsets.length !== starts.length || offsets.length === 0) return null
  return offsets.map((offset, i) => ({ distance: starts[i], offset }))
}

/** The point at `distance` along the line's baseline, clamped to its ends. */
export function pointAlong (line: ScanLine, distance: number): Point {
  const { baseline: b, distances: d } = line
  if (distance <= 0) return b[0]
  for (let i = 1; i < b.length; i++) {
    if (distance <= d[i]) {
      const step = d[i] - d[i - 1]
      const t = step === 0 ? 0 : (distance - d[i - 1]) / step
      return [b[i - 1][0] + t * (b[i][0] - b[i - 1][0]), b[i - 1][1] + t * (b[i][1] - b[i - 1][1])]
    }
  }
  return b[b.length - 1]
}

/** The band of the line between two distances along its baseline (whole line by default). */
export function lineBand (line: ScanLine, from = 0, to = line.length): Point[] {
  if (from <= 0 && to >= line.length) return line.polygon
  const lo = Math.max(0, Math.min(from, to))
  const hi = Math.min(line.length, Math.max(from, to))
  const points: Point[] = [pointAlong(line, lo)]
  line.distances.forEach((d, i) => { if (d > lo && d < hi) points.push(line.baseline[i]) })
  points.push(pointAlong(line, hi))
  if (hi - lo < 1e-6) points[1] = [points[0][0] + 1, points[0][1]]
  return band(points, Math.max(line.above, 1), Math.max(line.below, 1))
}

/** Distance along the baseline of the point of the baseline nearest to `p`. */
export function distanceAlong (line: ScanLine, p: Point): number {
  const { baseline: b, distances: d } = line
  let best = 0
  let bestDist = Infinity
  for (let i = 1; i < b.length; i++) {
    const [ax, ay] = b[i - 1]
    const dx = b[i][0] - ax
    const dy = b[i][1] - ay
    const len2 = dx * dx + dy * dy
    const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / len2))
    const dist = Math.hypot(ax + t * dx - p[0], ay + t * dy - p[1])
    if (dist < bestDist) {
      bestDist = dist
      best = d[i - 1] + t * (d[i] - d[i - 1])
    }
  }
  return best
}

/** UTF-16 offset of the (approximate) start of the word at `distance`; undefined without word starts. */
export function offsetAtDistance (line: ScanLine, distance: number): number | undefined {
  if (!line.words) return undefined
  let offset = line.words[0].offset
  for (const w of line.words) {
    if (w.distance <= distance + 0.5) offset = w.offset
    else break
  }
  return offset
}

/**
 * The span along the baseline that covers the text `[start, end)` (UTF-16 offsets), widened to
 * whole words; the whole line without word starts or offsets.
 */
export function rangeDistances (line: ScanLine, start?: number, end?: number): [number, number] {
  if (!line.words || (start === undefined && end === undefined)) return [0, line.length]
  const s = start ?? 0
  const e = end ?? line.text.length
  let from = 0
  let to = line.length
  for (const w of line.words) {
    if (w.offset <= s) from = w.distance
    if (w.offset >= e && w.distance < to) {
      to = w.distance
      break
    }
  }
  return to > from ? [from, to] : [0, line.length]
}

function inside (p: Point, polygon: readonly Point[]): boolean {
  let result = false
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i]
    const [xj, yj] = polygon[j]
    if ((yi > p[1]) !== (yj > p[1]) && p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi) result = !result
  }
  return result
}

function rectDistance (p: Point, r: Rect): number {
  const dx = Math.max(r.x - p[0], 0, p[0] - (r.x + r.width))
  const dy = Math.max(r.y - p[1], 0, p[1] - (r.y + r.height))
  return Math.hypot(dx, dy)
}

function segmentDistance (p: Point, a: Point, b: Point): number {
  const dx = b[0] - a[0]
  const dy = b[1] - a[1]
  const length2 = dx * dx + dy * dy
  const t = length2 > 0 ? Math.min(1, Math.max(0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2)) : 0
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))
}

/** Distance from `p` (outside the polygon) to the polygon's outline. */
function polygonDistance (p: Point, polygon: readonly Point[]): number {
  let best = Infinity
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    best = Math.min(best, segmentDistance(p, polygon[j], polygon[i]))
  }
  return best
}

/**
 * The line at `p` (scan pixels): one whose band contains it (the smallest when bands
 * overlap), else the one whose band is nearest within `tolerance` pixels; null otherwise.
 * The distance is to the band itself, so a slanted or curved line is not hit across the
 * empty corners of its bounding rectangle.
 */
export function lineAt (lines: readonly ScanLine[], p: Point, tolerance = 0): ScanLine | null {
  let hit: ScanLine | null = null
  for (const line of lines) {
    if (inside(p, line.polygon) && (!hit || line.bounds.width * line.bounds.height < hit.bounds.width * hit.bounds.height)) {
      hit = line
    }
  }
  if (hit || tolerance <= 0) return hit
  let best = tolerance
  for (const line of lines) {
    // The bounding rectangle is never farther than the band: a cheap first filter.
    if (rectDistance(p, line.bounds) > best) continue
    const d = polygonDistance(p, line.polygon)
    if (d <= best) {
      best = d
      hit = line
    }
  }
  return hit
}

/** The smallest rectangle around the rectangles (null for none). */
export function unionRect (rects: Rect[]): Rect | null {
  if (!rects.length) return null
  const x = Math.min(...rects.map(r => r.x))
  const y = Math.min(...rects.map(r => r.y))
  return {
    x,
    y,
    width: Math.max(...rects.map(r => r.x + r.width)) - x,
    height: Math.max(...rects.map(r => r.y + r.height)) - y
  }
}

export const polygonBounds = boundsOf

/** SVG `points` attribute of a polygon. */
export const svgPoints = (polygon: readonly Point[]) => polygon.map(p => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')
