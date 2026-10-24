import { describe, expect, it } from 'vitest'

import { heatmapRows, heatmapSpec, heatmapTableRows } from 'src/features/analytics/libraryHeatmap'
import {
  alignWindow, binCount, binWidthFor, fullRange, mainRange, outside, panWindow, selectedWindow, timelineBins,
  timelineRows, timelineSpec, zoomWindow
} from 'src/features/analytics/timeline'

// The publication timeline (#361): main range, bins of the visible window, its table, zoom and
// pan; and the period × library heatmap built on the same bins. Pure functions, no drawing.

/** One outlier (311), the main group 1600–1785 and one document in 2000 (215 years later). */
const YEARS = [
  { year: 311, count: 1 }, { year: 1600, count: 2 }, { year: 1690, count: 3 }, { year: 1785, count: 1 },
  { year: 2000, count: 1 }
]

describe('publication timeline', () => {
  it('opens on the group with most documents, in whole decades, and names what lies outside', () => {
    // 1600 → 1690 → 1785 are at most 100 years apart; 311 and 2000 are not.
    expect(mainRange(YEARS)).toEqual({ start: 1600, end: 1789 })
    expect(fullRange(YEARS)).toEqual({ start: 310, end: 2009 })
    expect(outside(YEARS, { start: 1600, end: 1789 })).toEqual({
      before: { count: 1, years: [311] }, after: { count: 1, years: [2000] }
    })
    expect(mainRange([])).toBeNull()
    expect(fullRange([])).toBeNull()
  })

  it('names outside years only when there are at most three of them', () => {
    const many = [1, 2, 3, 4].map(year => ({ year, count: 1 }))
    expect(outside(many, { start: 1000, end: 1009 }).before).toEqual({ count: 4, years: [] })
  })

  it('chooses the bin width from the visible window, not from the whole corpus', () => {
    expect(binWidthFor({ start: 1900, end: 1920 })).toBe(1)
    expect(binWidthFor({ start: 1600, end: 1789 })).toBe(5)
    expect(binWidthFor({ start: 1600, end: 2009 })).toBe(10)
    // The whole range including the outlier: coarse, but only when it is shown.
    expect(binWidthFor({ start: 310, end: 2009 })).toBe(50)
    expect(alignWindow({ start: 1851, end: 1902 }, 10)).toEqual({ start: 1850, end: 1909 })
  })

  it('counts each year in the bin it belongs to: 1909 in the 1900s, 1910 in the 1910s', () => {
    const years = [{ year: 1909, count: 2 }, { year: 1910, count: 3 }]
    expect(timelineBins(years, { start: 1900, end: 1919 }, 10)).toEqual([
      { start: 1900, endExclusive: 1910, label: '1900–1909', count: 2 },
      { start: 1910, endExclusive: 1920, label: '1910–1919', count: 3 }
    ])
    expect(timelineBins(years, { start: 1909, end: 1910 }, 1).map(b => [b.label, b.count])).toEqual([['1909', 2], ['1910', 3]])
  })

  it('lists the window in a table that collapses 3 or more empty bins and counts the documents outside', () => {
    const years = [{ year: 311, count: 1 }, { year: 1905, count: 4 }, { year: 1908, count: 1 }, { year: 1910, count: 2 },
      { year: 1919, count: 1 }]
    const window = { start: 1900, end: 1919 }
    const rows = timelineRows(timelineBins(years, window, 1), 1, outside(years, window))

    expect(rows.map(r => [r.label, r.count, r.note ?? ''])).toEqual([
      ['Before 1900 (year 311), not shown', 1, ''],
      ['1900–1904', 0, 'no documents (5 years)'],
      ['1905', 4, ''],
      ['1906', 0, ''],
      ['1907', 0, ''],
      ['1908', 1, ''],
      ['1909', 0, ''],
      ['1910', 2, ''],
      ['1911–1918', 0, 'no documents (8 years)'],
      ['1919', 1, '']
    ])
    expect([binCount(13, 10), binCount(1, 1), binCount(4, 25), binCount(2, 100)])
      .toEqual(['13 decades', '1 year', '4 bins of 25 years', '2 centuries'])
  })

  it('zooms around the centre and pans by half a window, never beyond the full range', () => {
    const bounds = { start: 310, end: 2009 }
    const main = { start: 1600, end: 1789 }
    expect(zoomWindow(main, 0.5, bounds)).toEqual({ start: 1648, end: 1742 })
    expect(zoomWindow(main, 2, bounds)).toEqual({ start: 1505, end: 1884 })
    expect(zoomWindow(main, 100, bounds)).toEqual(bounds)
    // At most down to 5 years.
    expect(zoomWindow({ start: 1900, end: 1904 }, 0.5, bounds)).toEqual({ start: 1900, end: 1904 })
    expect(panWindow(main, 1, bounds)).toEqual({ start: 1695, end: 1884 })
    expect(panWindow({ start: 310, end: 499 }, -1, bounds)).toEqual({ start: 310, end: 499 })
    expect(panWindow({ start: 1900, end: 2009 }, 1, bounds)).toEqual({ start: 1900, end: 2009 })
  })

  it('turns a dragged selection into the years it touches', () => {
    expect(selectedWindow(1905.2, 1910.7)).toEqual({ start: 1905, end: 1910 })
    expect(selectedWindow(1910.7, 1905.2)).toEqual({ start: 1905, end: 1910 })
    expect(selectedWindow(1900, 1900)).toBeNull()
    expect(selectedWindow(Number.NaN, 1900)).toBeNull()
  })

  it('marks every bin with documents and lets a period be selected by dragging', () => {
    const bins = timelineBins([{ year: 1905, count: 1 }, { year: 1912, count: 9000 }], { start: 1900, end: 1919 }, 10)
    const spec = timelineSpec(bins, 10, { start: 1900, end: 1919 }) as { layer: Record<string, unknown>[] }

    expect(spec.layer[0].params).toEqual([{ name: 'period', select: { type: 'interval', encodings: ['x'] } }])
    // The second layer marks the bins with documents at the bottom, so 1 is seen next to 9,000.
    expect(spec.layer[1].transform).toEqual([{ filter: 'datum.count > 0' }])
    expect(JSON.stringify(spec)).toContain('"title":"Publication year (decades)"')
    expect(JSON.stringify(spec)).toContain('"domain":[1900,1920]')
  })
})

describe('period × library heatmap', () => {
  const rows = [
    { library: 'mzk', kind: 'value' as const, totalDocuments: 3, years: [{ year: 1905, count: 2 }, { year: 1912, count: 1 }], unknownYearCount: 0 },
    { library: null, kind: 'unknown' as const, totalDocuments: 2, years: [{ year: 1931, count: 1 }], unknownYearCount: 1 }
  ]
  const window = { start: 1900, end: 1999 }

  it('bins every library like the timeline and names the remaining documents', () => {
    const heatmap = heatmapRows(rows, window, 10)

    expect(heatmap.map(r => r.label)).toEqual(['Moravian Library (mzk)', 'Unknown library'])
    expect(heatmap[0].bins.map(b => b.count)).toEqual([2, 1, 0, 0, 0, 0, 0, 0, 0, 0])
    expect(heatmapRows([{ ...rows[1], kind: 'other_or_unknown' }], window, 10)[0].label).toBe('Other or unknown library')
  })

  it('lists periods with a column per library, collapsing long empty periods', () => {
    const table = heatmapTableRows(heatmapRows(rows, window, 10), 10)

    expect(table.map(r => [r.label, r.counts, r.total, r.note ?? ''])).toEqual([
      ['1900–1909', [2, 0], 2, ''],
      ['1910–1919', [1, 0], 1, ''],
      ['1920–1929', [0, 0], 0, ''],
      ['1930–1939', [0, 1], 1, ''],
      ['1940–1999', [0, 0], 0, 'no documents (6 decades)']
    ])
  })

  it('draws a cell only where a library has documents', () => {
    const spec = heatmapSpec(heatmapRows(rows, window, 10), 10, window) as {
      data: { values: { library: string, period: string, count: number }[] }
      encoding: { y: { scale: { domain: string[] } } }
    }

    expect(spec.data.values.map(c => [c.library, c.period, c.count])).toEqual([
      ['Moravian Library (mzk)', '1900–1909', 2], ['Moravian Library (mzk)', '1910–1919', 1], ['Unknown library', '1930–1939', 1]
    ])
    // Every row keeps its place, also one without a cell in the window.
    expect(spec.encoding.y.scale.domain).toEqual(['Moravian Library (mzk)', 'Unknown library'])
  })
})
