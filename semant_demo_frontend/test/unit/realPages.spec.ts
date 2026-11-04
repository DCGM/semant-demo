import { readFileSync } from 'fs'
import { join } from 'path'
import { describe, expect, it } from 'vitest'

import type { LayoutStart } from 'src/generated/api'
import { parsePageLayout, type PageLayout } from 'src/features/documents/scan/pageLayout'
import {
  linesForRange, mapChunk, pageBreaks, pagesOf, textForLine, type ChunkLayoutMap
} from 'src/features/documents/correspondence/layoutMap'

// The text/scan correspondence (#544) on real PERO OCR pages and stored legacy chunks
// (#546): the page files and anchors the converter made of them
// (semant_demo_backend/tests/real_pages.py, kept current by its drift test). The browser's
// walk must agree with the importer's: an exact anchor gives an exact map reproducing every
// UTF-16 unit of the stored text, an approximate one whole lines only.

const FIXTURE = join(__dirname, '../../../semant_demo_backend/tests/fixtures/real_pages')
const read = (path: string) => readFileSync(join(FIXTURE, path), 'utf8')

interface RealChunk { id: string, order: number, fromPage: number, toPage: number, text: string }
interface RealDocument { documentId: string, pages: { pageId: string, label: string | null, pageType: string }[], chunks: RealChunk[] }

const documents = (JSON.parse(read('documents.json')) as { documents: RealDocument[] }).documents
const anchors = new Map<string, LayoutStart | null>(read('generated/anchors.jsonl').trim().split('\n')
  .map(line => JSON.parse(line) as { chunkId: string, layoutStart: LayoutStart | null })
  .map(a => [a.chunkId, a.layoutStart]))
const layouts = new Map<string, PageLayout>()
function layoutOf (documentId: string, pageId: string): PageLayout {
  const key = `${documentId}/${pageId}`
  if (!layouts.has(key)) layouts.set(key, parsePageLayout(JSON.parse(read(`generated/pages/${key}.json`)), pageId))
  return layouts.get(key)!
}

const byId = (id: string) => documents.find(d => d.documentId.startsWith(id))!
const NEWSPAPER = byId('0002097a')
const VOLUME_1906 = byId('00094a56')
const REPEATED = byId('000b03e0')

async function mapOf (document: RealDocument, chunk: RealChunk) {
  return mapChunk({ ...chunk, layoutStart: anchors.get(chunk.id) }, document.pages.map(p => p.pageId),
    (pageId) => Promise.resolve(layoutOf(document.documentId, pageId)))
}

const lineText = (document: RealDocument, pageId: string, lineId: string) =>
  layoutOf(document.documentId, pageId).lines.find(l => l.id === lineId)!.text

/** The chunk text rebuilt from the map: each piece's part of its line, then the separator. */
function rebuilt (document: RealDocument, map: ChunkLayoutMap, text: string) {
  let out = ''
  for (const piece of map.pieces) {
    out += text.slice(out.length, piece.start) // the separator, checked below
    out += lineText(document, piece.pageId, piece.lineId).slice(piece.lineStart, piece.lineEnd)
  }
  return out
}

describe('the browser walk on real pages', () => {
  it('maps every chunk as the importer anchored it', async () => {
    const seen: Record<string, number> = {}
    for (const document of documents) {
      for (const chunk of document.chunks) {
        const anchor = anchors.get(chunk.id)
        const map = await mapOf(document, chunk)
        if (!anchor) {
          expect(map).toBe('no_anchor')
          seen.none = (seen.none ?? 0) + 1
          continue
        }
        if (typeof map === 'string') throw new Error(`${chunk.id}: ${map}`)
        expect(map.precision).toBe(anchor.match)
        seen[anchor.match] = (seen[anchor.match] ?? 0) + 1
        if (anchor.match === 'exact') {
          expect(map.complete).toBe(true)
          expect(map.issues).toEqual([])
          expect(map.covered).toBe(chunk.text.length)
          expect(rebuilt(document, map, chunk.text)).toBe(chunk.text)
          // Between pieces only the separators: `\n` within a region, `\n\n` between regions and pages.
          map.pieces.slice(1).forEach((piece, i) => {
            expect(['\n', '\n\n']).toContain(chunk.text.slice(map.pieces[i].end, piece.start))
          })
        } else {
          expect(map.issues).toContain('approximate_anchor')
        }
      }
    }
    expect(seen).toEqual({ exact: 36, approximate: 1, none: 16 })
  })

  it('a line of the scan and its text find each other in both directions', async () => {
    let lines = 0
    for (const document of documents) {
      for (const chunk of document.chunks) {
        const map = await mapOf(document, chunk)
        if (typeof map === 'string' || map.precision !== 'exact') continue
        for (const piece of map.pieces) {
          lines++
          // Scan to text: the line, and the word clicked (its first character) as the point.
          const hit = textForLine(map, piece.pageId, piece.lineId, piece.lineStart)!
          expect(hit.precision).toBe('exact')
          expect(hit.point).toBe(piece.start)
          expect(hit.holdsOffset).toBe(true)
          // Text to scan: the line's text range gives exactly that line and range.
          expect(linesForRange(map, piece.start, piece.end)).toEqual([
            { pageId: piece.pageId, lineId: piece.lineId, start: piece.lineStart, end: piece.lineEnd }
          ])
        }
      }
    }
    expect(lines).toBeGreaterThan(600)
  })

  it('a word hyphenated across two lines highlights both lines', async () => {
    let words = 0
    for (const document of documents) {
      for (const chunk of document.chunks) {
        const map = await mapOf(document, chunk)
        if (typeof map === 'string' || map.precision !== 'exact') continue
        for (const m of chunk.text.matchAll(/(\p{L}+)-\n(\p{L}+)/gu)) {
          words++
          const targets = linesForRange(map, m.index!, m.index! + m[0].length)
          expect(targets).toHaveLength(2)
          expect(lineText(document, targets[0].pageId, targets[0].lineId).slice(targets[0].start, targets[0].end)).toBe(`${m[1]}-`)
          expect(lineText(document, targets[1].pageId, targets[1].lineId).slice(targets[1].start, targets[1].end)).toBe(m[2])
        }
      }
    }
    expect(words).toBeGreaterThan(50)
  })

  it('chunks across page breaks: ten of them, blank pages and a repeated caption', async () => {
    const [chunk] = VOLUME_1906.chunks
    const map = await mapOf(VOLUME_1906, chunk)
    if (typeof map === 'string') throw new Error(map)
    // The chunk's pages: the front matter, 0..10.
    const front = VOLUME_1906.pages.slice(0, 11)
    const pageIds = front.map(p => p.pageId)
    const blanks = front.filter(p => p.pageType === 'Blank').map(p => p.pageId)
    // The walk passes the blank pages without lines and goes on to the end of the chunk.
    expect(map.precision).toBe('exact')
    expect(pagesOf(map)).toEqual(pageIds.filter(id => layoutOf(VOLUME_1906.documentId, id).lines.length > 0))
    expect(pagesOf(map)).not.toEqual(expect.arrayContaining(blanks.slice(0, 4)))
    // A selection over the whole chunk covers every line of every page it is on.
    const all = linesForRange(map, 0, chunk.text.length)
    expect(new Set(all.map(t => t.pageId))).toEqual(new Set(pagesOf(map)))
    // The same caption on three pages: each occurrence is on its own page.
    const caption = 'Aus dem naturhistorischen Vereinsmuseum.'
    const pages = [...chunk.text.matchAll(new RegExp(caption.replace('.', '\\.'), 'g'))]
      .map(m => linesForRange(map, m.index!, m.index! + caption.length).map(t => t.pageId))
    expect(pages.map(p => p.length)).toEqual([1, 1, 1])
    expect(new Set(pages.flat()).size).toBe(3)
    // Page breaks where each later page's text begins (not at the chunk's start).
    const breaks = pageBreaks(map, id => layoutOf(VOLUME_1906.documentId, id).lines[0]?.id, chunk.text)
    expect(breaks.map(b => b.pageId)).toEqual(pagesOf(map))
    for (const b of breaks.slice(1)) expect(['\n\n']).toContain(chunk.text.slice(b.offset - 2, b.offset))
  })

  it('chunks crossing a page break show lines on both pages', async () => {
    let crossing = 0
    for (const chunk of VOLUME_1906.chunks.slice(1)) {
      const map = await mapOf(VOLUME_1906, chunk)
      if (typeof map === 'string' || pagesOf(map).length < 2) continue
      crossing++
      expect(map.precision).toBe('exact')
      const [first, second] = pagesOf(map)
      // A selection over the page break: the end of one page and the start of the next.
      const at = map.pieces.findIndex(p => p.pageId === second)
      const lines = linesForRange(map, map.pieces[at - 1].start, map.pieces[at].end)
      expect(lines.map(l => l.pageId)).toEqual([first, second])
      expect(chunk.text.slice(map.pieces[at - 1].end, map.pieces[at].start)).toBe('\n\n')
    }
    expect(crossing).toBeGreaterThanOrEqual(3)
  })

  it('an approximate map shows whole lines only', async () => {
    let approximate = 0
    for (const chunk of NEWSPAPER.chunks) {
      const map = await mapOf(NEWSPAPER, chunk)
      if (typeof map === 'string' || map.precision !== 'approximate') continue
      approximate++
      for (const target of linesForRange(map, 0, chunk.text.length)) {
        expect(target.start).toBeUndefined()
        expect(target.end).toBeUndefined()
      }
    }
    expect(approximate).toBe(1)
  })

  it('second copies of repeated chunks have no map', async () => {
    const seen = new Set<string>()
    let copies = 0
    for (const chunk of REPEATED.chunks) {
      if (seen.has(chunk.text)) {
        copies++
        expect(await mapOf(REPEATED, chunk)).toBe('no_anchor')
      }
      seen.add(chunk.text)
    }
    expect(copies).toBe(9)
  })
})
