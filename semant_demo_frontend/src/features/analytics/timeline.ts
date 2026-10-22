/**
 * The publication timeline of the corpus overview (#361): which years are visible, how they
 * are binned, and the rows and chart specification of the visible window.
 *
 * The backend sends documents per year (only years with documents). Everything here is
 * derived from those counts in the browser, so zooming and panning never ask the server:
 * they change only the visible window and its bin width, never the documents counted.
 *
 * - The **main range** is where most documents are: the years with documents are split
 *   wherever two consecutive ones are more than `OUTLIER_GAP` years apart, and the group with
 *   the most documents (widened to whole decades) is shown first. The rest is named, not
 *   dropped (`outside`).
 * - The **bin width** follows the visible window, not the whole corpus, so one outlier does
 *   not force coarse bins: the narrowest of `BIN_WIDTHS` that gives at most `MAX_BINS` bins.
 * - A window always covers whole bins, so no bin counts only part of its years.
 */
import type { VisualizationSpec } from 'vega-embed'
import type { YearCount } from 'src/generated/api'

/** Years with documents further apart than this separate the main range from outliers. */
export const OUTLIER_GAP = 100
export const BIN_WIDTHS = [1, 5, 10, 25, 50, 100, 250, 500, 1000]
export const MAX_BINS = 60
/** The narrowest window zooming in reaches, in years. */
export const MIN_SPAN = 5
const DECADE = 10

/** Inclusive first and last year. */
export interface YearWindow {
  start: number
  end: number
}

export interface TimelineBin {
  start: number
  endExclusive: number
  label: string
  count: number
}

export interface Outside {
  count: number
  /** The distinct years, when there are at most three of them (to name them). */
  years: number[]
}

export type TimelineRowKind = 'bin' | 'gap' | 'before' | 'after'

export interface TimelineRow {
  key: string
  kind: TimelineRowKind
  label: string
  count: number
  /** For a gap: "no documents (13 decades)". */
  note?: string
}

const span = (w: YearWindow) => w.end - w.start + 1
const floorTo = (year: number, width: number) => Math.floor(year / width) * width

/** The window widened to whole multiples of `width` (e.g. 1851–1902 → 1850–1909 for decades). */
export function alignWindow (window: YearWindow, width: number): YearWindow {
  return { start: floorTo(window.start, width), end: floorTo(window.end, width) + width - 1 }
}

/** The narrowest bin width that shows the window in at most `MAX_BINS` bins. */
export function binWidthFor (window: YearWindow): number {
  for (const width of BIN_WIDTHS) {
    const aligned = alignWindow(window, width)
    if (span(aligned) / width <= MAX_BINS) return width
  }
  return BIN_WIDTHS[BIN_WIDTHS.length - 1]
}

/** Every year with documents, in whole decades; null without years. */
export function fullRange (years: YearCount[]): YearWindow | null {
  if (!years.length) return null
  const all = years.map(y => y.year)
  return alignWindow({ start: Math.min(...all), end: Math.max(...all) }, DECADE)
}

/** The group of years holding the most documents, in whole decades; null without years. */
export function mainRange (years: YearCount[]): YearWindow | null {
  const sorted = [...years].sort((a, b) => a.year - b.year)
  if (!sorted.length) return null
  let best = { start: sorted[0].year, end: sorted[0].year, count: 0 }
  let group = { ...best }
  for (const [i, y] of sorted.entries()) {
    if (i > 0 && y.year - sorted[i - 1].year > OUTLIER_GAP) group = { start: y.year, end: y.year, count: 0 }
    group.end = y.year
    group.count += y.count
    if (group.count > best.count) best = { ...group }
  }
  return alignWindow(best, DECADE)
}

/** Documents before and after the window. */
export function outside (years: YearCount[], window: YearWindow): { before: Outside, after: Outside } {
  const side = (list: YearCount[]): Outside => ({
    count: list.reduce((n, y) => n + y.count, 0),
    years: list.length <= 3 ? list.map(y => y.year).sort((a, b) => a - b) : []
  })
  return {
    before: side(years.filter(y => y.year < window.start)),
    after: side(years.filter(y => y.year > window.end))
  }
}

export function binLabel (start: number, width: number): string {
  return width === 1 ? `${start}` : `${start}–${start + width - 1}`
}

/** "decade", "year", "5 years": one bin's width in words. */
export function widthName (width: number): string {
  if (width === 1) return 'year'
  if (width === DECADE) return 'decade'
  if (width === 100) return 'century'
  return `${width} years`
}

/** "decades", "single years", "bins of 25 years". */
export function binsName (width: number): string {
  if (width === 1) return 'single years'
  if (width === DECADE) return 'decades'
  if (width === 100) return 'centuries'
  return `bins of ${width} years`
}

/** All bins of the (aligned) window, empty ones included. */
export function timelineBins (years: YearCount[], window: YearWindow, width: number): TimelineBin[] {
  const counts = new Map<number, number>()
  for (const { year, count } of years) {
    if (year < window.start || year > window.end) continue
    const start = floorTo(year, width)
    counts.set(start, (counts.get(start) ?? 0) + count)
  }
  const bins: TimelineBin[] = []
  for (let start = window.start; start <= window.end; start += width) {
    bins.push({ start, endExclusive: start + width, label: binLabel(start, width), count: counts.get(start) ?? 0 })
  }
  return bins
}

/** Runs of this many empty bins or more are one table row. */
export const COLLAPSE_EMPTY = 3

function plural (n: number, width: number): string {
  const name = widthName(width)
  if (width !== 1 && width !== DECADE && width !== 100) return `${n} bins of ${name}`
  if (n === 1) return `1 ${name}`
  return `${n} ${name === 'century' ? 'centuries' : `${name}s`}`
}

/**
 * The table of the visible window: documents before it, its bins (3 or more consecutive empty
 * bins as one row, so gaps stay visible), documents after it. With the Unknown row the page
 * adds, the rows account for every document.
 */
export function timelineRows (bins: TimelineBin[], width: number, out: { before: Outside, after: Outside }): TimelineRow[] {
  const rows: TimelineRow[] = []
  const first = bins[0]?.start
  const last = bins[bins.length - 1]?.endExclusive
  const named = (o: Outside) => o.years.length ? ` (${o.years.length === 1 ? 'year' : 'years'} ${o.years.join(', ')})` : ''
  if (out.before.count && first !== undefined) {
    rows.push({ key: 'before', kind: 'before', label: `Before ${first}${named(out.before)}, not shown`, count: out.before.count })
  }
  for (let i = 0; i < bins.length;) {
    let j = i
    while (j < bins.length && bins[j].count === 0) j++
    if (j - i >= COLLAPSE_EMPTY) {
      rows.push({
        key: `gap-${bins[i].start}`,
        kind: 'gap',
        label: `${bins[i].start}–${bins[j - 1].endExclusive - 1}`,
        count: 0,
        note: `no documents (${plural(j - i, width)})`
      })
      i = j
    } else {
      const bin = bins[i]
      rows.push({ key: `bin-${bin.start}`, kind: 'bin', label: bin.label, count: bin.count })
      i++
    }
  }
  if (out.after.count && last !== undefined) {
    rows.push({ key: 'after', kind: 'after', label: `${last} and later${named(out.after)}, not shown`, count: out.after.count })
  }
  return rows
}

function clamp (window: YearWindow, bounds: YearWindow): YearWindow {
  const length = Math.min(span(window), span(bounds))
  const start = Math.min(Math.max(window.start, bounds.start), bounds.end - length + 1)
  return { start, end: start + length - 1 }
}

/** The window `factor` times as wide around the same centre (below 1: zoom in), inside `bounds`. */
export function zoomWindow (window: YearWindow, factor: number, bounds: YearWindow): YearWindow {
  const length = Math.max(MIN_SPAN, Math.round(span(window) * factor))
  const centre = (window.start + window.end) / 2
  const start = Math.round(centre - (length - 1) / 2)
  return clamp({ start, end: start + length - 1 }, bounds)
}

/** The window moved by half its width (direction -1: earlier, 1: later), inside `bounds`. */
export function panWindow (window: YearWindow, direction: -1 | 1, bounds: YearWindow): YearWindow {
  const shift = Math.max(1, Math.round(span(window) / 2)) * direction
  return clamp({ start: window.start + shift, end: window.end + shift }, bounds)
}

/** The years a selection between two positions on the year axis touches (year y spans [y, y + 1)). */
export function selectedWindow (from: number, to: number): YearWindow | null {
  if (!Number.isFinite(from) || !Number.isFinite(to) || from === to) return null
  return { start: Math.floor(Math.min(from, to)), end: Math.ceil(Math.max(from, to)) - 1 }
}

const SCHEMA = 'https://vega.github.io/schema/vega-lite/v6.json'
const HEIGHT = 220
/** A bin with documents is marked below the axis line, so a count of 1 is seen next to 10,000. */
const MARK_HEIGHT = 4

/**
 * Documents per bin of the visible window. Dragging across the chart selects a period
 * (signal `period`); every bin with documents has a small mark at the bottom.
 */
export function timelineSpec (bins: TimelineBin[], width: number, window: YearWindow): VisualizationSpec {
  const x = {
    field: 'start',
    type: 'quantitative',
    bin: { binned: true, step: width },
    title: `Publication year (${binsName(width)})`,
    scale: { domain: [window.start, window.end + 1], nice: false, zero: false },
    axis: { format: 'd', labelOverlap: true, tickMinStep: 1 }
  }
  const tooltip = [
    { field: 'label', type: 'nominal', title: width === 1 ? 'Year' : 'Years' },
    { field: 'count', type: 'quantitative', title: 'Documents', format: ',d' }
  ]
  return {
    $schema: SCHEMA,
    data: { values: bins },
    height: HEIGHT,
    layer: [
      {
        params: [{ name: 'period', select: { type: 'interval', encodings: ['x'] } }],
        mark: { type: 'bar', color: '#1976d2', tooltip: true },
        encoding: {
          x,
          x2: { field: 'endExclusive' },
          y: {
            field: 'count',
            type: 'quantitative',
            title: 'Documents',
            axis: { format: ',d', tickMinStep: 1 }
          },
          tooltip
        }
      },
      {
        transform: [{ filter: 'datum.count > 0' }],
        mark: { type: 'bar', color: '#0d47a1', tooltip: true },
        encoding: { x, x2: { field: 'endExclusive' }, y: { value: HEIGHT }, y2: { value: HEIGHT - MARK_HEIGHT }, tooltip }
      }
    ]
  }
}
