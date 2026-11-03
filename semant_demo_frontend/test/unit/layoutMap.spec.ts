import { describe, expect, it } from 'vitest'

import type { LayoutStart } from 'src/generated/api'
import { parsePageLayout, type PageLayout } from 'src/features/documents/scan/pageLayout'
import {
  linesForRange, mapChunk, pageBreaks, pagesOf, rangeOnPage, selectionRange, textForLine, type ChunkLayoutMap, type LayoutSource
} from 'src/features/documents/correspondence/layoutMap'

// The text/scan correspondence (#544) against documents serialized here with the importer's
// rules (docs/PAGE_LAYOUT.md): lines `\n` within a region, `\n\n` between regions and pages,
// chunks concatenated without separators, each chunk starting on a line character.

type Lines = string[][] // regions of line texts
const PAGES = ['p0', 'p1', 'p2', 'p3']

function layoutFile (pageId: string, regions: Lines) {
  return {
    schema: 'semant.page-layout',
    version: 1,
    pageId,
    image: { width: 1000, height: 1400 },
    regions: regions.map((lines, r) => ({
      id: `r${r}`,
      lines: lines.map((text, l) => ({ id: `r${r}-l${l}`, text, baseline: [[10, 100 + 40 * l], [900, 100 + 40 * l]], heights: [20, 8] }))
    }))
  }
}

function source (pages: Record<string, Lines | null>): { layoutOf: LayoutSource, layouts: Record<string, PageLayout | null>, reads: string[] } {
  const layouts = Object.fromEntries(Object.entries(pages).map(([id, regions]) => [id, regions ? parsePageLayout(layoutFile(id, regions), id) : null]))
  const reads: string[] = []
  return { layouts, reads, layoutOf: (id) => { reads.push(id); return Promise.resolve(layouts[id] ?? null) } }
}

/** The serialized document text and, per UTF-16 unit, its line and offset (null: separator). */
function serialize (pages: Record<string, Lines | null>) {
  let text = ''
  const owner: ({ pageId: string, lineId: string, offset: number } | null)[] = []
  for (const pageId of PAGES) {
    const regions = pages[pageId]
    if (!regions) continue
    regions.forEach((lines, r) => lines.forEach((line, l) => {
      if (text.length) {
        const sep = l === 0 ? '\n\n' : '\n'
        text += sep
        owner.push(...Array.from(sep, () => null))
      }
      text += line
      for (let i = 0; i < line.length; i++) owner.push({ pageId, lineId: `r${r}-l${l}`, offset: i })
    }))
  }
  return { text, owner }
}

/** Chunks cut from the serialized text at `cuts` (each on a line character), with their anchors. */
function chunksOf (pages: Record<string, Lines | null>, cuts: number[]) {
  const { text, owner } = serialize(pages)
  const bounds = [...cuts, text.length]
  return bounds.slice(0, -1).map((start, i) => {
    const o = owner[start]!
    const layoutStart: LayoutStart = { pageId: o.pageId, lineId: o.lineId, offset: o.offset, match: 'exact' }
    return { id: `c${i}`, text: text.slice(start, bounds[i + 1]), layoutStart, start, owner }
  })
}

async function map (chunk: Parameters<typeof mapChunk>[0], pages: Record<string, Lines | null>) {
  const result = await mapChunk(chunk, PAGES, source(pages).layoutOf)
  if (typeof result === 'string') throw new Error(result)
  return result
}

const DOC: Record<string, Lines | null> = {
  p0: [['ZPRÁVY'], ['První řádek odstavce,', 'druhý řádek se 😀 smajlíkem', 'a třetí.'], ['Další odstavec na straně.']],
  p1: [['Pokračování na druhé straně', 'Opakovaný text.'], ['Opakovaný text.', 'konec.']],
  p2: [],
  p3: [['Za prázdnou stranou.']]
}

describe('mapChunk', () => {
  it('reproduces every chunk exactly and round-trips every offset through its line', async () => {
    const { text } = serialize(DOC)
    // Chunks start on line characters: mid-line, at a region start, across pages, after a blank page.
    const cuts = [0, text.indexOf('řádek odstavce'), text.indexOf('Další'), text.indexOf('druhé straně'), text.indexOf('Opakovaný text.\n\nOpakovaný') + 3, text.indexOf('Za prázdnou')]
    for (const chunk of chunksOf(DOC, cuts)) {
      const m = await map(chunk, DOC)
      expect(m.precision).toBe('exact')
      expect(m.complete).toBe(true)
      expect(m.issues).toEqual([])
      expect(m.covered).toBe(chunk.text.length)
      for (let offset = 0; offset < chunk.text.length; offset++) {
        const o = chunk.owner[chunk.start + offset]
        const [target] = linesForRange(m, offset, offset)
        if (o === null) {
          // A separator: the caret is before the next line's first character, or at the end
          // of the last line when the chunk ends in separators (these test chunks are cut, not stripped).
          const next = chunk.owner.slice(chunk.start + offset, chunk.start + chunk.text.length).find(x => x !== null)
          expect(target.start).toBe(next ? 0 : m.pieces[m.pieces.length - 1].lineEnd)
          continue
        }
        expect(target).toMatchObject({ pageId: o.pageId, lineId: o.lineId, start: o.offset })
        const back = textForLine(m, o.pageId, o.lineId, o.offset)!
        expect(back.point).toBe(offset)
        expect(back.precision).toBe('exact')
      }
    }
  })

  it('counts UTF-16 units: a non-BMP character is two units in the chunk and the line', async () => {
    const { text } = serialize(DOC)
    const [chunk] = chunksOf(DOC, [text.indexOf('😀')])
    const m = await map(chunk, DOC)
    expect(m.pieces[0]).toMatchObject({ lineId: 'r1-l1', lineStart: 'druhý řádek se '.length, start: 0 })
    expect(textForLine(m, 'p0', 'r1-l1', 'druhý řádek se 😀 '.length)!.point).toBe(3)
    expect(linesForRange(m, 0, 2)).toEqual([{ pageId: 'p0', lineId: 'r1-l1', start: 15, end: 17 }])
  })

  it('keeps repeated text apart: the anchor, not the text, decides the line', async () => {
    const { text } = serialize(DOC)
    const second = text.lastIndexOf('Opakovaný text.')
    const [chunk] = chunksOf(DOC, [second])
    const m = await map(chunk, DOC)
    expect(m.pieces[0]).toMatchObject({ pageId: 'p1', lineId: 'r1-l0' })
    expect(textForLine(m, 'p1', 'r0-l1')).toBeNull()
  })

  it('walks across pages and over a page without lines, reading only the pages it needs', async () => {
    const { text } = serialize(DOC)
    const [chunk] = chunksOf(DOC, [text.indexOf('konec.')])
    const longer = { ...chunk, text: text.slice(text.indexOf('konec.')) }
    const s = source(DOC)
    const m = await mapChunk(longer, PAGES, s.layoutOf) as ChunkLayoutMap
    expect(pagesOf(m)).toEqual(['p1', 'p3'])
    expect(m.precision).toBe('exact')
    expect(s.reads).toEqual(['p1', 'p2', 'p3'])
    const first = chunksOf(DOC, [0])[0]
    const s0 = source(DOC)
    await mapChunk({ ...first, text: 'ZPRÁVY' }, PAGES, s0.layoutOf)
    expect(s0.reads).toEqual(['p0'])
  })

  it('splits a multi-page range into the lines of every page, beginning first', async () => {
    const { text } = serialize(DOC)
    const [chunk] = chunksOf(DOC, [text.indexOf('a třetí')])
    const m = await map({ ...chunk, text: text.slice(text.indexOf('a třetí'), text.indexOf('Opakovaný')) }, DOC)
    const lines = linesForRange(m, 2, m.length)
    expect(lines.map(l => `${l.pageId}/${l.lineId}`)).toEqual(['p0/r1-l2', 'p0/r2-l0', 'p1/r0-l0'])
    expect(lines[0]).toMatchObject({ start: 2, end: 'a třetí.'.length })
    expect(rangeOnPage(m, 'p1')).toEqual({ start: m.length - 'Pokračování na druhé straně'.length - 1, end: m.length - 1 })
    // The page break is at the first character from the new page, not in the separator.
    const breaks = pageBreaks(m, id => ({ p0: 'r0-l0', p1: 'r0-l0' } as Record<string, string>)[id])
    expect(breaks).toEqual([{ offset: text.indexOf('Pokračování') - text.indexOf('a třetí'), pageId: 'p1', precision: 'exact' }])
    expect(chunk.text.slice(breaks[0].offset)).toMatch(/^Pokračování/)
  })

  it('marks a break at a chunk start only where the page starts', async () => {
    const [atTop] = chunksOf(DOC, [0])
    const top = await map({ ...atTop, text: 'ZPRÁVY' }, DOC)
    expect(pageBreaks(top, () => 'r0-l0')).toEqual([{ offset: 0, pageId: 'p0', precision: 'exact' }])
    const { text } = serialize(DOC)
    const [mid] = chunksOf(DOC, [text.indexOf('Další')])
    expect(pageBreaks(await map(mid, DOC), () => 'r0-l0').map(b => b.offset)).not.toContain(0)
  })

  it('maps an approximate anchor to whole lines only, never to characters', async () => {
    const { text } = serialize(DOC)
    const [chunk] = chunksOf(DOC, [text.indexOf('První')])
    // OCR and chunk text differ slightly.
    const edited = { ...chunk, text: chunk.text.slice(0, 60).replace('řádek', 'radek'), layoutStart: { ...chunk.layoutStart, match: 'approximate' as const } }
    const m = await map(edited, DOC)
    expect(m.precision).toBe('approximate')
    expect(m.issues).toContain('approximate_anchor')
    expect(linesForRange(m, 3, 30)).toEqual([{ pageId: 'p0', lineId: 'r1-l0' }, { pageId: 'p0', lineId: 'r1-l1' }])
    const hit = textForLine(m, 'p0', 'r1-l1', 6)!
    expect(hit).toMatchObject({ precision: 'approximate', point: hit.start })
  })

  it('puts an approximate page break at the nearest word start', async () => {
    const { text } = serialize(DOC)
    const [chunk] = chunksOf(DOC, [text.indexOf('Další')])
    // Two characters lost before the page end: the walk reaches page 1 two units late.
    const shifted = text.slice(text.indexOf('Další'), text.indexOf('Opakovaný')).replace('na straně', 'na strně').replace('Pokračování', 'Pokraovní')
    const m = await map({ ...chunk, text: shifted, layoutStart: { ...chunk.layoutStart, match: 'approximate' } }, DOC)
    const raw = m.pieces.find(p => p.pageId === 'p1')!.start
    expect(shifted.slice(raw)).not.toMatch(/^Pokra/)
    const [mark] = pageBreaks(m, () => 'r0-l0', shifted)
    expect(mark).toMatchObject({ pageId: 'p1', precision: 'approximate' })
    expect(shifted.slice(mark.offset)).toMatch(/^Pokraovní/)
  })

  it('treats an exact anchor whose walk differs from the text as approximate', async () => {
    const { text } = serialize(DOC)
    const [chunk] = chunksOf(DOC, [text.indexOf('První')])
    const m = await map({ ...chunk, text: chunk.text.replace('druhý', 'DRUHÝ') }, DOC)
    expect(m.precision).toBe('approximate')
    expect(m.issues).toContain('text_mismatch')
    // A separator where the walk has none is a mismatch too.
    const joined = await map({ ...chunk, text: chunk.text.replace('odstavce,\n', 'odstavce, ') }, DOC)
    expect(joined.issues).toContain('text_mismatch')
  })

  it('stops at a page without a layout and reports the part it covered', async () => {
    const pages = { ...DOC, p1: null }
    const { text } = serialize(DOC)
    const [chunk] = chunksOf(DOC, [text.indexOf('Další')])
    const long = { ...chunk, text: text.slice(text.indexOf('Další'), text.indexOf('konec.')) }
    const m = await map(long, pages)
    expect(m.complete).toBe(false)
    expect(m.issues).toContain('missing_layout')
    expect(m.covered).toBe('Další odstavec na straně.'.length)
    expect(linesForRange(m, m.covered + 5, m.covered + 9)).toEqual([])
  })

  it('treats malformed lines in a page file as approximate', async () => {
    const s = source(DOC)
    s.layouts.p0 = { ...s.layouts.p0!, skippedLines: 1 }
    const [chunk] = chunksOf(DOC, [0])
    const m = await mapChunk({ ...chunk, text: 'ZPRÁVY' }, PAGES, s.layoutOf) as ChunkLayoutMap
    expect(m.precision).toBe('approximate')
    expect(m.issues).toEqual(['malformed_layout'])
  })

  it('gives no map without an anchor, on an unknown page or line, a bad offset or a missing first layout', async () => {
    const { layoutOf } = source(DOC)
    const chunk = { id: 'c', text: 'ZPRÁVY' }
    const at = (a: Partial<LayoutStart>) => ({ ...chunk, layoutStart: { pageId: 'p0', lineId: 'r0-l0', offset: 0, match: 'exact' as const, ...a } })
    expect(await mapChunk(chunk, PAGES, layoutOf)).toBe('no_anchor')
    expect(await mapChunk({ ...chunk, layoutStart: null }, PAGES, layoutOf)).toBe('no_anchor')
    expect(await mapChunk(at({ pageId: 'elsewhere' }), PAGES, layoutOf)).toBe('unknown_page')
    expect(await mapChunk(at({ lineId: 'r9-l9' }), PAGES, layoutOf)).toBe('unknown_line')
    expect(await mapChunk(at({ offset: 99 }), PAGES, layoutOf)).toBe('bad_offset')
    expect(await mapChunk(at({ pageId: 'p2', lineId: 'x' }), PAGES, layoutOf)).toBe('unknown_line')
    expect(await mapChunk(at({}), PAGES, () => Promise.resolve(null))).toBe('missing_layout')
  })

  it('passes on an aborted layout read', async () => {
    const [chunk] = chunksOf(DOC, [0])
    await expect(mapChunk(chunk, PAGES, () => Promise.reject(new DOMException('Aborted', 'AbortError')))).rejects.toThrow('Aborted')
  })
})

describe('selectionRange', () => {
  const chunks = [{ id: 'a', order: 3, text: 'abcd' }, { id: 'b', order: 4, text: 'efg' }, { id: 'c', order: 6, text: 'xyz' }]
  it('anchors on the first chunk and measures the end across the following ones, in either direction', () => {
    expect(selectionRange({ chunkId: 'a', charOffset: 1 }, { chunkId: 'a', charOffset: 3 }, chunks)).toEqual({ chunkId: 'a', start: 1, end: 3 })
    expect(selectionRange({ chunkId: 'b', charOffset: 2 }, { chunkId: 'a', charOffset: 1 }, chunks)).toEqual({ chunkId: 'a', start: 1, end: 6 })
    expect(selectionRange({ chunkId: 'a', charOffset: 3 }, { chunkId: 'a', charOffset: 1 }, chunks)).toEqual({ chunkId: 'a', start: 1, end: 3 })
  })
  it('ends at a gap in chunk order and refuses unknown chunks', () => {
    expect(selectionRange({ chunkId: 'a', charOffset: 1 }, { chunkId: 'c', charOffset: 2 }, chunks)).toEqual({ chunkId: 'a', start: 1, end: 7 })
    expect(selectionRange({ chunkId: 'a', charOffset: 1 }, { chunkId: 'zz', charOffset: 2 }, chunks)).toBeNull()
  })
})
