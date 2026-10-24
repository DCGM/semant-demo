/**
 * Publication period × source library (#361, optional heatmap): documents per library in the
 * periods the timeline shows. The backend sends documents per year for each library (and for
 * the remaining documents); this module bins them like the timeline (`timeline.ts`), so the
 * heatmap follows the timeline's zoom without asking the server again.
 *
 * Counts are raw document counts. Every period with documents is coloured (the lightest colour
 * means 1), an empty one is left blank.
 */
import type { VisualizationSpec } from 'vega-embed'
import type { LibraryYears } from 'src/generated/api'
import { libraryLabel } from './corpusOverview'
import { COLLAPSE_EMPTY, binCount, binsName, timelineBins, type TimelineBin, type YearWindow } from './timeline'

export interface HeatmapRow {
  key: string
  label: string
  bins: TimelineBin[]
}

export function rowLabel (row: LibraryYears): string {
  if (row.kind === 'value' && row.library !== null) return libraryLabel(row.library)
  return row.kind === 'unknown' ? 'Unknown library' : 'Other or unknown library'
}

/** One row per library (and the remaining documents) with its bins of the shown window. */
export function heatmapRows (rows: LibraryYears[], window: YearWindow, width: number): HeatmapRow[] {
  return rows.map((row, i) => ({
    key: row.library ?? `\u0000rest-${i}`,
    label: rowLabel(row),
    bins: timelineBins(row.years, window, width)
  }))
}

export interface HeatmapTableRow {
  key: string
  kind: 'bin' | 'gap'
  label: string
  note?: string
  /** Documents per heatmap row, in the order of the rows. */
  counts: number[]
  total: number
}

/**
 * The table of the heatmap: one row per period (columns: the libraries), with 3 or more
 * consecutive periods without any document as one row, as in the timeline's table.
 */
export function heatmapTableRows (rows: HeatmapRow[], width: number): HeatmapTableRow[] {
  const periods = rows[0]?.bins ?? []
  const counts = periods.map((_, p) => rows.map(row => row.bins[p].count))
  const totals = counts.map(c => c.reduce((a, b) => a + b, 0))
  const table: HeatmapTableRow[] = []
  for (let i = 0; i < periods.length;) {
    let j = i
    while (j < periods.length && totals[j] === 0) j++
    if (j - i >= COLLAPSE_EMPTY) {
      table.push({
        key: `gap-${periods[i].start}`,
        kind: 'gap',
        label: `${periods[i].start}–${periods[j - 1].endExclusive - 1}`,
        note: `no documents (${binCount(j - i, width)})`,
        counts: rows.map(() => 0),
        total: 0
      })
      i = j
    } else {
      table.push({ key: `bin-${periods[i].start}`, kind: 'bin', label: periods[i].label, counts: counts[i], total: totals[i] })
      i++
    }
  }
  return table
}

const SCHEMA = 'https://vega.github.io/schema/vega-lite/v6.json'
const ROW_HEIGHT = 26
const COLORS = ['#bbdefb', '#0d47a1']

/** Coloured cells for the periods with documents; rows in the given order. */
export function heatmapSpec (rows: HeatmapRow[], width: number, window: YearWindow): VisualizationSpec {
  const cells = rows.flatMap((row, order) => row.bins
    .filter(bin => bin.count > 0)
    .map(bin => ({ library: row.label, order, start: bin.start, endExclusive: bin.endExclusive, period: bin.label, count: bin.count })))
  return {
    $schema: SCHEMA,
    data: { values: cells },
    height: Math.max(rows.length, 1) * ROW_HEIGHT,
    mark: { type: 'rect', tooltip: true, stroke: '#ffffff', strokeWidth: 0.5 },
    encoding: {
      x: {
        field: 'start',
        type: 'quantitative',
        bin: { binned: true, step: width },
        title: `Publication year (${binsName(width)})`,
        scale: { domain: [window.start, window.end + 1], nice: false, zero: false },
        axis: { format: 'd', labelOverlap: true, tickMinStep: 1, grid: true }
      },
      x2: { field: 'endExclusive' },
      y: {
        field: 'library',
        type: 'nominal',
        title: null,
        sort: { field: 'order', order: 'ascending' },
        scale: { domain: rows.map(row => row.label) },
        // Long names are shortened on the axis (the tooltip and the table have them in full).
        axis: { labelLimit: 140 }
      },
      color: {
        field: 'count',
        type: 'quantitative',
        title: 'Documents',
        scale: { type: 'sqrt', range: COLORS, zero: false },
        // Below the chart, so the cells keep the width on a phone.
        legend: { format: ',d', tickMinStep: 1, orient: 'bottom', gradientLength: 160 }
      },
      tooltip: [
        { field: 'library', type: 'nominal', title: 'Library' },
        { field: 'period', type: 'nominal', title: width === 1 ? 'Year' : 'Years' },
        { field: 'count', type: 'quantitative', title: 'Documents', format: ',d' }
      ]
    }
  }
}
