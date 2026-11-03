import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick, ref, shallowRef } from 'vue'

import type { DocumentPage } from 'src/generated/api'
import { createLayoutCache } from 'src/features/documents/scan/pageAssets'
import { parsePageLayout, type PageLayout } from 'src/features/documents/scan/pageLayout'
import { NOTICES, useTextScanSync, type SyncChunk } from 'src/features/documents/correspondence/useTextScanSync'
import DocumentTextPane from 'src/features/documents/viewer/DocumentTextPane.vue'
import { revealDelta } from 'src/features/documents/viewer/textReveal'

// The synchronization of the text and scan panes (#544): explicit interactions only, the
// other pane moved through its smart focus, stale requests dropped, and reads bounded to
// what an interaction needs.

async function until (condition: () => boolean) {
  for (let i = 0; i < 50 && !condition(); i++) await new Promise(resolve => setTimeout(resolve, 0))
  expect(condition()).toBe(true)
}

const page = (i: number, layout = true): DocumentPage => ({
  pageId: `p${i}`, order: i, label: String(i), imageUrl: `/img/${i}`, layoutUrl: layout ? `/layout/${i}` : null
})
const PAGES = [page(0), page(1), page(2, false), page(3)]

function layout (pageId: string, regions: string[][]): PageLayout {
  return parsePageLayout({
    schema: 'semant.page-layout',
    version: 1,
    pageId,
    regions: regions.map((lines, r) => ({
      id: `r${r}`, lines: lines.map((text, l) => ({ id: `r${r}-l${l}`, text, baseline: [[0, 10 * l], [100, 10 * l]] }))
    }))
  }, pageId)
}

const LAYOUTS: Record<string, PageLayout> = {
  p0: layout('p0', [['Nadpis'], ['První řádek', 'druhý řádek']]),
  p1: layout('p1', [['třetí řádek'], ['Na straně 1.']]),
  p3: layout('p3', [['Za stranou bez řádků.']])
}

/** c0 crosses from page 0 to page 1 (exact); c1 is on page 1 (approximate); c2 has no anchor. */
const CHUNKS: SyncChunk[] = [
  { id: 'c0', order: 0, fromPage: 0, toPage: 1, text: 'Nadpis\n\nPrvní řádek\ndruhý řádek\n\ntřetí řádek', layoutStart: { pageId: 'p0', lineId: 'r0-l0', offset: 0, match: 'exact' } },
  { id: 'c1', order: 1, fromPage: 1, toPage: 1, text: 'Na strane 1.', layoutStart: { pageId: 'p1', lineId: 'r1-l0', offset: 0, match: 'approximate' } },
  { id: 'c2', order: 2, fromPage: 3, toPage: 3, text: 'Bez kotvy.' }
]

function setup (options: { chunks?: SyncChunk[], pageChunks?: (order: number) => Promise<SyncChunk[]>, complete?: boolean, delay?: Record<string, Promise<void>> } = {}) {
  const reads: string[] = []
  const layouts = createLayoutCache(async (p, signal) => {
    reads.push(p.pageId)
    await options.delay?.[p.pageId]
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    return LAYOUTS[p.pageId]
  })
  const chunks = shallowRef<SyncChunk[]>(options.chunks ?? CHUNKS)
  const pages = shallowRef<DocumentPage[]>(PAGES)
  const focusScan = vi.fn(() => Promise.resolve(true))
  const revealText = vi.fn()
  const read = options.pageChunks ?? (() => Promise.resolve([] as SyncChunk[]))
  const pageChunks = vi.fn(async (order: number) => ({ chunks: await read(order), complete: options.complete ?? true }))
  const sync = useTextScanSync({ pages, layouts: () => layouts, chunks, pageChunks, focusScan, revealText })
  return { sync, reads, focusScan, revealText, pageChunks, chunks, pages }
}

describe('useTextScanSync', () => {
  it('shows a text range on every line of every page it covers and focuses its beginning', async () => {
    const { sync, focusScan, reads } = setup()
    const text = CHUNKS[0].text
    await sync.showTextOnScan({ chunkId: 'c0', start: text.indexOf('řádek'), end: text.length })
    expect(sync.scanHighlights.value.map(h => `${h.pageId}/${h.lineId}`)).toEqual(['p0/r1-l0', 'p0/r1-l1', 'p1/r0-l0'])
    expect(sync.scanHighlights.value[0]).toMatchObject({ start: 6, end: 11, approximate: false })
    // The beginning only: the first page, its lines, the first line's part.
    expect(focusScan).toHaveBeenCalledTimes(1)
    expect(focusScan).toHaveBeenCalledWith({ pageId: 'p0', lineIds: ['r1-l0', 'r1-l1'], start: 6, end: undefined })
    expect(sync.notice.value).toBe('')
    // Only the pages of the chunk were read, never the page without a layout or later ones.
    expect(reads).toEqual(['p0', 'p1'])
  })

  it('highlights a range across chunks, approximate parts as whole lines, and says so', async () => {
    const { sync } = setup()
    const len = CHUNKS[0].text.length
    await sync.showTextOnScan({ chunkId: 'c0', start: len - 3, end: len + 4 })
    expect(sync.scanHighlights.value).toEqual([
      { pageId: 'p1', lineId: 'r0-l0', start: 8, end: 11, approximate: false },
      { pageId: 'p1', lineId: 'r1-l0', start: undefined, end: undefined, approximate: true }
    ])
    expect(sync.notice.value).toBe(NOTICES.approximateText)
  })

  it('marks the clicked line in the text, and degrades to text only without an anchor', async () => {
    const { sync, focusScan } = setup()
    await sync.showTextOnScan({ chunkId: 'c0', start: 10, end: 10 }, { markLine: true })
    expect(sync.textFocus.value).toEqual({ range: { chunkId: 'c0', start: 8, end: 19 }, approximate: false })
    await sync.showTextOnScan({ chunkId: 'c2', start: 2, end: 2 }, { markLine: true })
    expect(sync.textFocus.value).toBeNull()
    expect(sync.scanHighlights.value).toEqual([])
    expect(sync.notice.value).toBe(NOTICES.noScanPlace)
    expect(focusScan).toHaveBeenCalledTimes(1)
  })

  it('finds a clicked scan line in the text at the word clicked, from the chunks shown first', async () => {
    const { sync, revealText, pageChunks } = setup()
    await sync.showLineInText({ pageId: 'p0', lineId: 'r1-l1', offset: 6 })
    expect(sync.textFocus.value).toEqual({ range: { chunkId: 'c0', start: 20, end: 31 }, approximate: false })
    expect(revealText).toHaveBeenCalledWith({ chunkId: 'c0', start: 26 })
    expect(pageChunks).not.toHaveBeenCalled()
    // An approximate line: its start, flagged.
    await sync.showLineInText({ pageId: 'p1', lineId: 'r1-l0', offset: 3 })
    expect(sync.textFocus.value).toEqual({ range: { chunkId: 'c1', start: 0, end: 12 }, approximate: true })
    expect(revealText).toHaveBeenLastCalledWith({ chunkId: 'c1', start: 0 })
    expect(sync.notice.value).toBe(NOTICES.approximateLine)
  })

  it('reads the page chunks when the line is not in the text shown, and says when no chunk has it', async () => {
    const { sync, revealText, pageChunks } = setup({ chunks: [CHUNKS[0]], pageChunks: (order) => Promise.resolve(order === 1 ? [CHUNKS[1]] : []) })
    await sync.showLineInText({ pageId: 'p1', lineId: 'r1-l0' })
    expect(pageChunks).toHaveBeenCalledWith(1)
    expect(revealText).toHaveBeenCalledWith({ chunkId: 'c1', start: 0 })
    await sync.showLineInText({ pageId: 'p3', lineId: 'r0-l0' })
    expect(sync.textFocus.value).toBeNull()
    expect(sync.notice.value).toBe(NOTICES.lineNotInText)
  })

  it('gives a click on a line shared by two chunks to the chunk holding the word clicked', async () => {
    // Page 1's first line "třetí řádek": chunk a ends after "třetí ", chunk b begins at "řádek".
    const a: SyncChunk = { id: 'a', order: 0, fromPage: 0, toPage: 1, text: 'druhý řádek\n\ntřetí ', layoutStart: { pageId: 'p0', lineId: 'r1-l1', offset: 0, match: 'exact' } }
    const b: SyncChunk = { id: 'b', order: 1, fromPage: 1, toPage: 1, text: 'řádek', layoutStart: { pageId: 'p1', lineId: 'r0-l0', offset: 6, match: 'exact' } }
    const { sync, revealText } = setup({ chunks: [a, b] })
    await sync.showLineInText({ pageId: 'p1', lineId: 'r0-l0', offset: 6 })
    expect(sync.textFocus.value).toEqual({ range: { chunkId: 'b', start: 0, end: 5 }, approximate: false })
    expect(revealText).toHaveBeenLastCalledWith({ chunkId: 'b', start: 0 })
    await sync.showLineInText({ pageId: 'p1', lineId: 'r0-l0', offset: 0 })
    expect(revealText).toHaveBeenLastCalledWith({ chunkId: 'a', start: a.text.indexOf('třetí') })
    // Without the word clicked, the whole line from its first chunk.
    await sync.showLineInText({ pageId: 'p1', lineId: 'r0-l0' })
    expect(sync.textFocus.value?.range.chunkId).toBe('a')
  })

  it('does not call a line missing when the page has more chunks than could be read', async () => {
    const { sync } = setup({ chunks: [], complete: false })
    await sync.showLineInText({ pageId: 'p3', lineId: 'r0-l0' })
    expect(sync.textFocus.value).toBeNull()
    expect(sync.notice.value).toBe(NOTICES.lineLookupIncomplete)
  })

  it('goes to the first text of a page even when only a later passage of it is shown', async () => {
    // Page 1 holds the end of c0, then c1; a deep link has shown only c1.
    const { sync, revealText, pageChunks } = setup({ chunks: [CHUNKS[1]], pageChunks: (order) => Promise.resolve(order === 1 ? CHUNKS.slice(0, 2) : []) })
    await sync.onScanPage(PAGES[1], 1)
    expect(pageChunks).toHaveBeenCalledWith(1)
    expect(revealText).toHaveBeenCalledWith({ chunkId: 'c0', start: CHUNKS[0].text.indexOf('třetí') })
  })

  it('drops an interaction overtaken by a newer one: a slow layout never moves a pane later', async () => {
    let release: () => void = () => undefined
    const slow = new Promise<void>(resolve => { release = resolve })
    const onPage3 = { ...CHUNKS[2], text: 'Za stranou bez řádků.', layoutStart: { pageId: 'p3', lineId: 'r0-l0', offset: 0, match: 'exact' as const } }
    const { sync, focusScan, revealText } = setup({ chunks: [...CHUNKS.slice(0, 2), onPage3], delay: { p3: slow } })
    const first = sync.showTextOnScan({ chunkId: 'c2', start: 0, end: 3 })
    await sync.showTextOnScan({ chunkId: 'c0', start: 0, end: 3 })
    release()
    await first
    expect(focusScan).toHaveBeenCalledTimes(1)
    expect(focusScan).toHaveBeenCalledWith(expect.objectContaining({ pageId: 'p0' }))
    expect(sync.scanHighlights.value.map(h => h.pageId)).toEqual(['p0'])
    // Cancelling (the reader scrolls the text) drops a pending one too.
    const pending = sync.showLineInText({ pageId: 'p1', lineId: 'r1-l0' })
    sync.cancel()
    await pending
    expect(revealText).not.toHaveBeenCalled()
  })

  it('follows page navigation in the scan viewer to the page text, but not its own focus requests', async () => {
    const { sync, revealText, focusScan } = setup()
    // The text asks the scan viewer to open page 1; the viewer reports the page change.
    focusScan.mockImplementation(async () => { await sync.onScanPage(PAGES[1], 1); return true })
    await sync.showTextOnScan({ chunkId: 'c1', start: 0, end: 2 })
    expect(revealText).not.toHaveBeenCalled()
    expect(sync.currentPageId.value).toBe('p1')
    // The reader goes to page 0 in the scan viewer: the text follows to its first text.
    await sync.onScanPage(PAGES[0], 0)
    expect(revealText).toHaveBeenCalledWith({ chunkId: 'c0', start: 0 })
    // Initial pages (before a deep link is handled) are not followed.
    revealText.mockClear()
    await sync.onScanPage(PAGES[1], 1, { follow: false })
    expect(revealText).not.toHaveBeenCalled()
  })

  it('falls back to the stored page range for a page without line positions', async () => {
    const { sync, revealText } = setup()
    await sync.onScanPage(PAGES[3], 3)
    expect(revealText).toHaveBeenCalledWith({ chunkId: 'c2', start: 0 })
    expect(sync.notice.value).toBe(NOTICES.coarsePage)
    const empty = setup({ chunks: [] })
    await empty.sync.onScanPage(PAGES[3], 3)
    expect(empty.sync.notice.value).toBe(NOTICES.pageWithoutText)
  })

  it('marks page starts and the current page in the chunks near the page shown', async () => {
    const { sync, reads } = setup()
    await sync.onScanPage(PAGES[1], 1, { follow: false })
    await until(() => !!sync.pageMarks.value.c1)
    const c0 = CHUNKS[0].text
    expect(sync.pageMarks.value.c0).toEqual({
      range: { start: c0.indexOf('třetí'), end: c0.length },
      breaks: [
        { offset: 0, pageId: 'p0', label: 'Page 0', approximate: false },
        { offset: c0.indexOf('třetí'), pageId: 'p1', label: 'Page 1', approximate: false }
      ]
    })
    expect(sync.pageMarks.value.c1).toEqual({ range: { start: 0, end: 12 }, breaks: [] })
    // Pages 0 and 1 only, never page 3 two pages away.
    expect(reads.sort()).toEqual(['p0', 'p1'])
  })

  it('reports a layout that fails to load, and forgets everything with another document', async () => {
    const pages = ref<DocumentPage[]>(PAGES)
    const layouts = createLayoutCache(() => Promise.reject(new Error('offline')))
    const sync = useTextScanSync({
      pages,
      layouts: () => layouts,
      chunks: shallowRef(CHUNKS),
      pageChunks: () => Promise.resolve({ chunks: [], complete: true }),
      focusScan: () => Promise.resolve(true),
      revealText: () => undefined
    })
    await sync.showTextOnScan({ chunkId: 'c0', start: 0, end: 2 })
    expect(sync.notice.value).toBe(NOTICES.layoutFailed)
    pages.value = []
    await nextTick()
    expect(sync.notice.value).toBe('')
    expect(sync.available.value).toBe(false)
  })
})

describe('revealDelta (smart focus in the text)', () => {
  const view = { top: 100, bottom: 700 }
  it('does not move a target visible with its margin', () => {
    expect(revealDelta({ top: 300, bottom: 320 }, view)).toBe(0)
    expect(revealDelta({ top: 148, bottom: 168 }, view)).toBe(0)
  })
  it('moves a target near an edge by the least distance, and an unseen one to the middle', () => {
    expect(revealDelta({ top: 120, bottom: 140 }, view)).toBe(-28)
    expect(revealDelta({ top: 660, bottom: 680 }, view)).toBe(28)
    expect(revealDelta({ top: 2000, bottom: 2020 }, view)).toBe(1610)
    expect(revealDelta({ top: -500, bottom: -480 }, view)).toBe(-890)
  })
  it('keeps a tall target\'s top in view', () => {
    expect(revealDelta({ top: 400, bottom: 1200 }, view)).toBe(252)
  })
})

describe('DocumentTextPane page marks', () => {
  afterEach(() => { document.body.innerHTML = '' })

  it('shows page starts outside the text, tints the current page and marks approximate places', async () => {
    const wrapper = mount(DocumentTextPane, {
      props: {
        chunks: [{ id: 'c', order: 0, text: 'Konec strany.\n\nNová strana.' }],
        pageMarks: { c: { range: { start: 15, end: 27 }, breaks: [{ offset: 15, pageId: 'p2', label: 'Page 2' }, { offset: 0, pageId: 'p1', label: 'Page 1', approximate: true }] } },
        activeRange: { chunkId: 'c', start: 0, end: 5 },
        activeApproximate: true
      },
      attachTo: document.body
    })
    const breaks = wrapper.findAll('.page-break')
    expect(breaks.map(b => b.attributes('aria-label'))).toEqual(['Page 1 (approximate position)', 'Page 2'])
    expect(breaks.map(b => b.attributes('role'))).toEqual(['separator', 'separator'])
    // The labels are not text: the chunk's text content is unchanged.
    expect(wrapper.find('[data-chunk-id="c"]').text()).toBe('Konec strany.\n\nNová strana.')
    expect(wrapper.find('.page-break + .text-segment').attributes('data-start')).toBe('0')
    expect(wrapper.findAll('.is-current-page').map(s => s.text())).toEqual(['Nová strana.'])
    expect(wrapper.find('.has-approximate-passage .is-active-passage').text()).toBe('Konec')
    wrapper.unmount()
  })
})
