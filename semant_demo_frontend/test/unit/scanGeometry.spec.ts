import { describe, expect, it, vi } from 'vitest'

import type { DocumentPage } from 'src/generated/api'
import {
  LayoutFormatError, distanceAlong, lineAt, lineBand, offsetAtDistance, parsePageLayout, polygonBounds,
  rangeDistances, wordOffsets
} from 'src/features/documents/scan/pageLayout'
import {
  FIT_PADDING, KEEP_VISIBLE, clampTransform, fitTransform, keepCenter, scaleLimits, smartFocus, toScan, toViewer, zoomAt
} from 'src/features/documents/scan/viewport'
import { createLayoutCache } from 'src/features/documents/scan/pageAssets'
import { adjacentLine, findPage, pageName } from 'src/features/documents/scan/pageNavigation'

const PAGE = '4a2c533a-aa49-11e3-9f73-d485646517a0'

/** The documented example line (docs/PAGE_LAYOUT.md) and a skewed and a curved one. */
const file = (overrides: Record<string, unknown> = {}) => ({
  schema: 'semant.page-layout',
  version: 1,
  pageId: PAGE,
  image: { width: 1378, height: 2000 },
  regions: [
    {
      id: 'r004',
      lines: [
        {
          id: 'r004-l003',
          text: 'Ročník XIX.',
          baseline: [[100, 158], [124, 158], [146, 157], [166, 157], [187, 157], [207, 157], [229, 157], [255, 157]],
          heights: [19, 7],
          wordStarts: [0, 99]
        },
        { id: 'r004-l004', text: 'skewed line', baseline: [[100, 300], [400, 240]], heights: [20, 10] },
        { id: 'r004-l005', text: 'no heights', baseline: [[100, 400], [250, 420], [400, 400]], heights: null }
      ]
    }
  ],
  ...overrides
})

describe('parsePageLayout', () => {
  it('reads lines in serialization order with their band around the baseline', () => {
    const layout = parsePageLayout(file(), PAGE)

    expect(layout.image).toEqual({ width: 1378, height: 2000 })
    expect(layout.lines.map(l => [l.id, l.index, l.regionId])).toEqual([
      ['r004-l003', 0, 'r004'], ['r004-l004', 1, 'r004'], ['r004-l005', 2, 'r004']
    ])
    const first = layout.lines[0]
    // Horizontal baseline: 19 px above and 7 px below.
    expect(first.bounds.y).toBeCloseTo(157 - 19, 0)
    expect(first.bounds.y + first.bounds.height).toBeCloseTo(158 + 7, 0)
    expect(first.bounds.x).toBeCloseTo(100, 0)
    expect(first.length).toBeCloseTo(155, 0)
  })

  it('follows a skewed baseline instead of an axis-aligned box', () => {
    const skewed = parsePageLayout(file(), PAGE).lines[1]
    // The upper edge starts above the first point, perpendicular to the baseline.
    const [ux, uy] = skewed.polygon[0]
    const dir = [300, -60].map(v => v / Math.hypot(300, 60))
    expect((ux - 100) * dir[0] + (uy - 300) * dir[1]).toBeCloseTo(0, 6)
    expect(Math.hypot(ux - 100, uy - 300)).toBeCloseTo(20, 6)
    expect(uy).toBeLessThan(300)
    // A point between the two ends inside the band, one well above it outside.
    expect(lineAt([skewed], [250, 265])?.id).toBe('r004-l004')
    expect(lineAt([skewed], [250, 200])).toBeNull()
  })

  it('estimates missing heights from the other lines of the page', () => {
    const lines = parsePageLayout(file(), PAGE).lines
    // The median line of the page by total height (of [19, 7] and [20, 10]: the upper one).
    expect([lines[2].above, lines[2].below]).toEqual([20, 10])
  })

  it('rejects other formats and other pages, and leaves out malformed or repeated lines', () => {
    expect(() => parsePageLayout(file({ version: 2 }), PAGE)).toThrow(LayoutFormatError)
    expect(() => parsePageLayout(file({ schema: 'other' }), PAGE)).toThrow(LayoutFormatError)
    expect(() => parsePageLayout(file(), 'another-page')).toThrow(LayoutFormatError)
    expect(() => parsePageLayout(null, PAGE)).toThrow(LayoutFormatError)

    const layout = parsePageLayout(file({
      image: null,
      regions: [{
        id: 'r1',
        lines: [
          { id: 'a', text: 'kept', baseline: [[0, 10], [50, 10]], heights: [5, 2] },
          { id: 'a', text: 'repeated id', baseline: [[0, 30], [50, 30]], heights: [5, 2] },
          { id: 'b', text: 'no baseline', baseline: [], heights: [5, 2] },
          { id: 'c', text: 'bad point', baseline: [[0, 'x']], heights: [5, 2] },
          { text: 'no id', baseline: [[0, 50], [50, 50]] },
          { id: 'd', text: 'one point', baseline: [[10, 70]], heights: [5, 2] }
        ]
      }]
    }), PAGE)
    expect(layout.lines.map(l => l.id)).toEqual(['a', 'd'])
    expect(layout.skippedLines).toBe(4)
    expect(layout.image).toBeNull()
    expect(layout.lines[1].length).toBe(0)
  })

  it('accepts an empty page (cover, blank page)', () => {
    expect(parsePageLayout(file({ regions: [] }), PAGE).lines).toEqual([])
  })
})

describe('approximate words', () => {
  it('finds word starts by the #463 rule in UTF-16 units', () => {
    expect(wordOffsets('Ročník XIX.')).toEqual([0, 7])
    expect(wordOffsets('Frýdek-Místek')).toEqual([0, 7])
    // A non-BMP character before a word counts two UTF-16 units.
    expect(wordOffsets('😀 Ahoj 𝐀b')).toEqual([3, 8])
  })

  it('maps a position on the line to the start of the word under it', () => {
    const line = parsePageLayout(file(), PAGE).lines[0]
    expect(line.words).toEqual([{ distance: 0, offset: 0 }, { distance: 99, offset: 7 }])
    expect(offsetAtDistance(line, 10)).toBe(0)
    expect(offsetAtDistance(line, 98.8)).toBe(7)
    expect(offsetAtDistance(line, 140)).toBe(7)
    expect(distanceAlong(line, [200, 140])).toBeCloseTo(100, 0)
  })

  it('has no word positions when the file has none or they do not match the text', () => {
    const lines = parsePageLayout(file(), PAGE).lines
    expect(lines[1].words).toBeNull()
    expect(offsetAtDistance(lines[1], 50)).toBeUndefined()
    const mismatched = parsePageLayout(file({
      regions: [{ id: 'r', lines: [{ id: 'x', text: 'one two three', baseline: [[0, 0], [100, 0]], heights: [5, 2], wordStarts: [0, 40] }] }]
    }), PAGE).lines[0]
    expect(mismatched.words).toBeNull()
  })

  it('highlights whole words of a text range, or the whole line without word starts', () => {
    const [first, skewed] = parsePageLayout(file(), PAGE).lines
    expect(rangeDistances(first, 7, 11)).toEqual([99, first.length])
    expect(rangeDistances(first, 2, 5)).toEqual([0, 99])
    expect(rangeDistances(first)).toEqual([0, first.length])
    expect(rangeDistances(skewed, 2, 5)).toEqual([0, skewed.length])
    const part = polygonBounds(lineBand(first, 99, first.length))
    expect(part.x).toBeGreaterThan(190)
    expect(part.x + part.width).toBeCloseTo(255, 0)
    expect(lineBand(first)).toBe(first.polygon)
  })
})

describe('lineAt', () => {
  it('prefers a containing band, else the nearest within the tolerance', () => {
    const lines = parsePageLayout(file(), PAGE).lines
    expect(lineAt(lines, [150, 150])?.id).toBe('r004-l003')
    expect(lineAt(lines, [150, 175])).toBeNull()
    expect(lineAt(lines, [150, 175], 12)?.id).toBe('r004-l003')
    expect(lineAt(lines, [1000, 1000], 12)).toBeNull()
  })
})

describe('viewport', () => {
  const image = { width: 1000, height: 2000 }
  const viewer = { width: 600, height: 500 }

  it('fits the whole page centered', () => {
    const t = fitTransform(image, viewer)
    expect(t.scale).toBeCloseTo((500 - 2 * FIT_PADDING) / 2000)
    expect(t.x + image.width * t.scale / 2).toBeCloseTo(300)
    expect(t.y).toBeCloseTo(FIT_PADDING)
    expect(fitTransform(image, { width: 0, height: 0 })).toEqual({ scale: 1, x: 0, y: 0 })
  })

  it('zooms about a fixed point within the limits', () => {
    const t = fitTransform(image, viewer)
    const limits = scaleLimits(image, viewer)
    const anchor = [123, 321] as const
    const zoomed = zoomAt(t, 2, anchor, limits)
    expect(zoomed.scale).toBeCloseTo(t.scale * 2)
    // The scan point under the anchor stays under it.
    expect(toScan(zoomed, anchor)[0]).toBeCloseTo(toScan(t, anchor)[0])
    expect(toScan(zoomed, anchor)[1]).toBeCloseTo(toScan(t, anchor)[1])
    expect(zoomAt(t, 1000, anchor, limits).scale).toBe(limits.max)
    expect(zoomAt(t, 0.001, anchor, limits).scale).toBe(limits.min)
  })

  it('keeps part of the page in view when panned far away', () => {
    const t = clampTransform({ scale: 1, x: -5000, y: 5000 }, image, viewer)
    expect(t.x).toBe(KEEP_VISIBLE - image.width)
    expect(t.y).toBe(viewer.height - KEEP_VISIBLE)
  })

  it('keeps the center of a zoomed page when the viewer is resized', () => {
    const t = { scale: 1.5, x: -200, y: -300 }
    const center = toScan(t, [300, 250])
    const after = keepCenter(t, viewer, { width: 400, height: 700 })
    expect(toViewer(after, center)).toEqual([200, 350])
    expect(after.scale).toBe(1.5)
  })
})

describe('smartFocus', () => {
  const viewer = { width: 600, height: 400 }
  const at1 = { scale: 1, x: 0, y: 0 }

  it('leaves a target that is visible and readable alone', () => {
    expect(smartFocus(at1, { x: 100, y: 100, width: 300, height: 30 }, viewer)).toBeNull()
  })

  it('pans by the least distance that brings the target in with a margin', () => {
    const below = smartFocus(at1, { x: 100, y: 500, width: 300, height: 30 }, viewer, { margin: 20 })
    expect(below).toEqual({ scale: 1, x: 0, y: 400 - 20 - 530 })
    const left = smartFocus(at1, { x: -50, y: 100, width: 100, height: 30 }, viewer, { margin: 20 })
    expect(left).toEqual({ scale: 1, x: 70, y: 0 })
  })

  it('aligns a target larger than the viewer at its start', () => {
    const t = smartFocus(at1, { x: 50, y: 50, width: 900, height: 30 }, viewer, { margin: 20 })
    expect(t).toEqual({ scale: 1, x: -30, y: 0 })
  })

  it('zooms in only when the target is too small to read, and never out', () => {
    const small = { scale: 0.2, x: 0, y: 0 }
    const t = smartFocus(small, { x: 100, y: 100, width: 400, height: 30 }, viewer, {
      minReadableHeight: 10, readableHeight: 20, limits: { min: 0.1, max: 4 }
    })!
    expect(t.scale).toBeCloseTo(20 / 30)
    // Now visible within the margin.
    const top = 100 * t.scale + t.y
    expect(top).toBeGreaterThanOrEqual(24 - 1e-9)
    expect(top + 30 * t.scale).toBeLessThanOrEqual(400 - 24 + 1e-9)
    // A wide line is zoomed only as far as it still fits across.
    const wide = smartFocus(small, { x: 0, y: 0, width: 2000, height: 30 }, viewer, { readableHeight: 20 })!
    expect(wide.scale).toBeCloseTo(0.276)
    // Already large: never zoomed out to fit.
    const big = smartFocus({ scale: 3, x: 0, y: 0 }, { x: 10, y: 10, width: 100, height: 50 }, viewer)
    expect(big?.scale ?? 3).toBe(3)
  })
})

describe('layout cache', () => {
  const page = (id: string): DocumentPage => ({ pageId: id, order: 0, layoutUrl: `/api/x/${id}/layout` })
  const layoutOf = (id: string) => ({ pageId: id, image: null, lines: [], skippedLines: 0 })

  it('reads each page once and keeps a bounded number of layouts', async () => {
    const load = vi.fn(async (p: DocumentPage) => layoutOf(p.pageId))
    const cache = createLayoutCache(load, 2)
    await Promise.all([cache.get(page('a')), cache.get(page('a'))])
    expect(load).toHaveBeenCalledTimes(1)
    await cache.get(page('b'))
    await cache.get(page('a')) // most recently used again
    await cache.get(page('c'))
    expect(cache.size).toBe(2)
    expect(cache.peek('b')).toBeNull()
    expect(cache.peek('a')).not.toBeNull()
  })

  it('aborts a request once every caller has gone, and not before', async () => {
    const signals: AbortSignal[] = []
    const load = vi.fn((p: DocumentPage, signal?: AbortSignal) => new Promise<ReturnType<typeof layoutOf>>((resolve) => {
      signals.push(signal!)
      setTimeout(() => resolve(layoutOf(p.pageId)), 5)
    }))
    const cache = createLayoutCache(load)
    const one = new AbortController()
    const two = new AbortController()
    const first = cache.get(page('a'), one.signal)
    const second = cache.get(page('a'), two.signal)
    one.abort()
    await expect(first).rejects.toMatchObject({ name: 'AbortError' })
    expect(signals[0].aborted).toBe(false)
    two.abort()
    await expect(second).rejects.toMatchObject({ name: 'AbortError' })
    expect(signals[0].aborted).toBe(true)
  })
})

describe('page navigation', () => {
  const pages: DocumentPage[] = [
    { pageId: 'p0', order: 0, label: '[1]', pageType: 'FrontCover' },
    { pageId: 'p1', order: 1, label: '1' },
    { pageId: 'p2', order: 2, label: '6' },
    { pageId: 'p3', order: 3, label: null }
  ]

  it('finds a page by printed label first, then by position', () => {
    expect(findPage(pages, '6')).toBe(2)
    expect(findPage(pages, ' [1] ')).toBe(0)
    expect(findPage(pages, '4')).toBe(3)
    expect(findPage(pages, '9')).toBeNull()
    expect(findPage(pages, '')).toBeNull()
  })

  it('names pages by label and special type', () => {
    expect(pageName(pages[0], 0)).toBe('Page [1], front cover')
    expect(pageName(pages[3], 3)).toBe('Page 4')
  })

  it('steps through lines and stops at the ends', () => {
    const lines = parsePageLayout(file(), PAGE).lines
    expect(adjacentLine(lines, null, 1)?.id).toBe('r004-l003')
    expect(adjacentLine(lines, null, -1)?.id).toBe('r004-l005')
    expect(adjacentLine(lines, 'r004-l003', 1)?.id).toBe('r004-l004')
    expect(adjacentLine(lines, 'r004-l005', 1)).toBeNull()
    expect(adjacentLine([], null, 1)).toBeNull()
  })
})
