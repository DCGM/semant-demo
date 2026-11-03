import { computed, nextTick, ref, shallowRef, watch, type Ref } from 'vue'
import type { DocumentPage } from 'src/generated/api'
import { isAbortError } from 'src/shared/api'
import type { FocusRequest, ScanHighlight, ScanTarget } from '../scan/DocumentImagePane.vue'
import type { LayoutCache } from '../scan/pageAssets'
import { pageName } from '../scan/pageNavigation'
import type { ChunkPageMarks } from '../viewer/documentTextPane'
import { rangeByChunk, type ChunkRange } from '../viewer/readerOffsets'
import {
  linesForRange, mapChunk, pageBreaks, rangeOnPage, textForLine,
  type ChunkLayoutMap, type LineTarget, type MappableChunk, type NoMapReason, type TextHit
} from './layoutMap'

// Bidirectional synchronization of the text and scan panes (#544). Only explicit interactions
// move the other pane: a click or selection in the text, a click or keyboard step on a scan
// line, page navigation in the scan viewer, a deep link. Scrolling, panning and zooming are
// never followed, and each pane moves only as far as needed (smart focus: the scan viewer's
// `focus`, the text pane's `revealRange`). A newer interaction cancels an older one still
// waiting for its data, so a slow response never moves a pane afterwards.
//
// Maps (layoutMap.ts) are built for the chunks an interaction needs and for the chunks near
// the page shown, from layouts read through the scan viewer's cache: never the layouts of
// all earlier pages, and never the whole document's text.

export interface SyncChunk extends MappableChunk {
  order: number
  fromPage: number
  toPage: number
}

/** The active passage in the text and whether its place is approximate. */
export interface TextFocus {
  range: ChunkRange
  approximate: boolean
}

export interface TextScanSyncOptions<T extends SyncChunk> {
  /** The manifest's pages; empty for a text-only document. */
  pages: Ref<DocumentPage[]>
  /** The layouts' cache shared with the scan viewer. */
  layouts: () => LayoutCache
  /** The chunks the text shows, in document order. */
  chunks: Ref<T[]>
  /**
   * Reads (and adds to `chunks`) the chunks whose page range includes page `order`;
   * `complete` false when the page has more than could be read.
   */
  pageChunks: (order: number) => Promise<{ chunks: T[], complete: boolean }>
  /** The scan viewer's focus request (it opens the page and focuses the lines smartly). */
  focusScan: (request: FocusRequest) => Promise<boolean>
  /** Brings a place in the text into view smartly, once the chunk is shown. */
  revealText: (at: { chunkId: string, start: number }) => void
}

export const NOTICES = {
  approximateText: 'The OCR text differs from the document text here: whole lines are shown, not exact words.',
  approximateLine: 'The OCR line differs from the document text: its place in the text is approximate.',
  partial: 'Only part of this text was found on the page scans.',
  noScanPlace: 'No place on the page scans is known for this text.',
  lineNotInText: 'This line was not found in the document text.',
  lineLookupIncomplete: 'This line was not found in the passages read for this page; the page has more than could be searched.',
  pageWithoutText: 'No document text is known on this page.',
  coarsePage: 'The text of this page has no line positions: it is shown from the passage that covers the page.',
  layoutFailed: 'The text lines of a page could not be loaded.'
} as const

export function useTextScanSync<T extends SyncChunk> (o: TextScanSyncOptions<T>) {
  const maps = shallowRef(new Map<string, ChunkLayoutMap | NoMapReason>())
  /** The first line id of each page whose layout was read, for page breaks. */
  const firstLines = new Map<string, string | undefined>()
  const scanHighlights = shallowRef<ScanHighlight[]>([])
  const textFocus = shallowRef<TextFocus | null>(null)
  const notice = ref('')
  const currentPageId = ref<string | null>(null)

  let interaction: AbortController | null = null
  let marking: AbortController | null = null
  /** The page a focus request of ours opens: the scan viewer's change to it is not followed. */
  let ownPage: string | null = null

  const pageIds = computed(() => o.pages.value.map(p => p.pageId))
  const pageIndex = computed(() => new Map(pageIds.value.map((id, i) => [id, i])))
  const available = computed(() => o.pages.value.length > 0)

  watch(o.pages, () => {
    cancel()
    marking?.abort()
    maps.value = new Map()
    firstLines.clear()
    scanHighlights.value = []
    textFocus.value = null
    notice.value = ''
  })

  /** Starts an explicit interaction: the previous one, if still waiting, gives up. */
  function begin (): AbortSignal {
    interaction?.abort()
    interaction = new AbortController()
    return interaction.signal
  }

  /** Cancels a pending interaction (e.g. the reader started scrolling the text). */
  function cancel () {
    interaction?.abort()
    interaction = null
  }

  const layoutOf = (signal: AbortSignal) => async (pageId: string) => {
    const page = o.pages.value[pageIndex.value.get(pageId) ?? -1]
    if (!page?.layoutUrl) return null
    const layout = await o.layouts().get(page, signal)
    firstLines.set(pageId, layout.lines[0]?.id)
    return layout
  }

  /** The chunk's map, built once (a failed layout read rejects and is tried again later). */
  async function mapOf (chunk: T, signal: AbortSignal): Promise<ChunkLayoutMap | NoMapReason> {
    const known = maps.value.get(chunk.id)
    if (known) return known
    const pages = o.pages.value
    const result = await mapChunk(chunk, pageIds.value, layoutOf(signal))
    if (pages === o.pages.value) maps.value = new Map(maps.value).set(chunk.id, result)
    return result
  }

  /** The parts of a range in each chunk it covers (a caret: its chunk alone). */
  function parts (range: ChunkRange): { chunk: T, start: number, end: number }[] {
    const chunks = o.chunks.value
    if (range.end <= range.start) {
      const chunk = chunks.find(c => c.id === range.chunkId)
      return chunk ? [{ chunk, start: range.start, end: range.start }] : []
    }
    const byChunk = rangeByChunk(range, chunks)
    return chunks.filter(c => byChunk[c.id]).map(c => ({ chunk: c, ...byChunk[c.id] }))
  }

  const failed = (signal: AbortSignal, e: unknown) => {
    if (signal.aborted || isAbortError(e)) return
    notice.value = NOTICES.layoutFailed
  }

  /**
   * Text to scan: highlights every line of `range` (on every page) and focuses the first;
   * with `markLine`, also marks the text of the line it begins in (a click in the text).
   */
  async function showTextOnScan (range: ChunkRange, { markLine = false } = {}): Promise<void> {
    if (!available.value) return
    const signal = begin()
    try {
      const lines: (LineTarget & { approximate: boolean })[] = []
      let approximate = false
      let missing = false
      let firstMap: ChunkLayoutMap | null = null
      for (const part of parts(range)) {
        const map = await mapOf(part.chunk, signal)
        if (signal.aborted) return
        if (typeof map === 'string') {
          missing = true
          continue
        }
        firstMap ??= map
        const found = linesForRange(map, part.start, part.end)
        if (!found.length || part.end > map.covered) missing = true
        if (found.length && map.precision !== 'exact') approximate = true
        lines.push(...found.map(l => ({ ...l, approximate: map.precision !== 'exact' })))
      }
      if (!lines.length || !firstMap) {
        scanHighlights.value = []
        if (markLine) textFocus.value = null
        notice.value = NOTICES.noScanPlace
        return
      }
      const first = lines[0]
      scanHighlights.value = lines.map(l => ({ pageId: l.pageId, lineId: l.lineId, start: l.start, end: l.end, approximate: l.approximate }))
      if (markLine) {
        const hit = textForLine(firstMap, first.pageId, first.lineId)
        textFocus.value = hit ? { range: { chunkId: hit.chunkId, start: hit.start, end: hit.end }, approximate: hit.precision !== 'exact' } : null
      } else {
        textFocus.value = null
      }
      notice.value = approximate ? NOTICES.approximateText : missing ? NOTICES.partial : ''
      ownPage = first.pageId
      try {
        await o.focusScan({
          pageId: first.pageId,
          lineIds: lines.filter(l => l.pageId === first.pageId).map(l => l.lineId),
          start: first.start,
          end: lines.length === 1 ? first.end : undefined
        })
      } finally {
        ownPage = null
      }
    } catch (e) {
      failed(signal, e)
    }
  }

  const covering = (index: number) => (c: T) => c.fromPage <= index && index <= c.toPage

  /**
   * The chunks that may hold page `index`'s text: those shown first, then those read for the
   * page. `lookup.complete` turns false when the page has more chunks than could be read.
   */
  async function * candidates (index: number, signal: AbortSignal, lookup: { complete: boolean }): AsyncGenerator<T> {
    const tried = new Set<string>()
    for (const c of o.chunks.value.filter(covering(index))) {
      tried.add(c.id)
      yield c
    }
    const read = await o.pageChunks(index)
    if (signal.aborted) return
    lookup.complete = read.complete
    for (const c of read.chunks.filter(covering(index))) {
      if (!tried.has(c.id)) yield c
    }
  }

  /** Scan to text: marks the line's text and brings it into view. */
  async function showLineInText (target: ScanTarget): Promise<void> {
    const signal = begin()
    const index = pageIndex.value.get(target.pageId)
    if (index === undefined) return
    const show = async (hit: TextHit) => {
      textFocus.value = { range: { chunkId: hit.chunkId, start: hit.start, end: hit.end }, approximate: hit.precision !== 'exact' }
      scanHighlights.value = []
      notice.value = hit.precision === 'exact' ? '' : NOTICES.approximateLine
      await nextTick()
      if (!signal.aborted) o.revealText({ chunkId: hit.chunkId, start: hit.point })
    }
    try {
      const lookup = { complete: true }
      // A line shared by two chunks belongs, for a click, to the chunk holding the word
      // clicked; the first chunk with any of the line is kept in case none holds it.
      let fallback: TextHit | null = null
      for await (const chunk of candidates(index, signal, lookup)) {
        if (!chunk.layoutStart) continue
        const map = await mapOf(chunk, signal)
        if (signal.aborted) return
        if (typeof map === 'string') continue
        const hit = textForLine(map, target.pageId, target.lineId, target.offset)
        if (!hit) continue
        if (hit.holdsOffset !== false) {
          await show(hit)
          return
        }
        fallback ??= hit
      }
      if (signal.aborted) return
      if (fallback) {
        await show(fallback)
        return
      }
      textFocus.value = null
      notice.value = lookup.complete ? NOTICES.lineNotInText : NOTICES.lineLookupIncomplete
    } catch (e) {
      failed(signal, e)
    }
  }

  /**
   * The scan viewer shows another page. With `follow` (the reader navigated in the scan
   * viewer) the text goes to the page's first text, unless the change is ours (a focus request
   * from the text). The first text is found among all the page's chunks in document order,
   * not only among those shown (a deep link may have shown a later passage of the page).
   */
  async function onScanPage (page: DocumentPage, index: number, { follow = true } = {}): Promise<void> {
    currentPageId.value = page.pageId
    void prepareMarks(index)
    if (!follow || ownPage === page.pageId) return
    const signal = begin()
    try {
      const read = await o.pageChunks(index)
      if (signal.aborted) return
      const byId = new Map<string, T>()
      for (const c of [...o.chunks.value, ...read.chunks].filter(covering(index))) byId.set(c.id, c)
      const ordered = [...byId.values()].sort((a, b) => a.order - b.order)
      for (const chunk of ordered) {
        if (!chunk.layoutStart) continue
        const map = await mapOf(chunk, signal)
        if (signal.aborted) return
        const on = typeof map === 'string' ? null : rangeOnPage(map, page.pageId)
        if (!on) continue
        // Highlights stay: a selection spanning pages is still shown on the page it continues on.
        notice.value = ''
        await nextTick()
        if (!signal.aborted) o.revealText({ chunkId: chunk.id, start: on.start })
        return
      }
      // No line positions for this page: its stored page range is all there is.
      const coarse = ordered.find(c => c.fromPage === index) ?? ordered[0] ?? null
      notice.value = coarse ? NOTICES.coarsePage : NOTICES.pageWithoutText
      if (coarse) {
        await nextTick()
        if (!signal.aborted) o.revealText({ chunkId: coarse.id, start: 0 })
      }
    } catch (e) {
      failed(signal, e)
    }
  }

  /** The scan viewer's change to this page comes from a focus request of ours (not the reader). */
  const isOwnPageChange = (pageId: string) => ownPage === pageId

  /** Builds the maps of the shown chunks near page `index`, for its marks in the text. */
  async function prepareMarks (index: number): Promise<void> {
    marking?.abort()
    const controller = new AbortController()
    marking = controller
    const near = o.chunks.value.filter(c => c.layoutStart && !maps.value.has(c.id) && c.toPage >= index - 1 && c.fromPage <= index + 1)
    for (const chunk of near) {
      try {
        await mapOf(chunk, controller.signal)
      } catch {
        return
      }
      if (controller.signal.aborted) return
    }
  }

  // Chunks read later (a page opened, more text) get their marks too.
  watch(o.chunks, () => {
    const index = currentPageId.value === null ? undefined : pageIndex.value.get(currentPageId.value)
    if (index !== undefined) void prepareMarks(index)
  })

  const pageLabel = (pageId: string) => {
    const index = pageIndex.value.get(pageId)
    return index === undefined ? 'Page' : pageName(o.pages.value[index], index)
  }

  /** Per chunk shown: its part on the current page and where pages begin in it. */
  const pageMarks = computed<Record<string, ChunkPageMarks>>(() => {
    const out: Record<string, ChunkPageMarks> = {}
    for (const chunk of o.chunks.value) {
      const map = maps.value.get(chunk.id)
      if (!map || typeof map === 'string') continue
      const breaks = pageBreaks(map, id => firstLines.get(id), chunk.text).map(b => ({
        offset: b.offset, pageId: b.pageId, label: pageLabel(b.pageId), approximate: b.precision !== 'exact'
      }))
      const range = currentPageId.value ? rangeOnPage(map, currentPageId.value) : null
      if (breaks.length || range) out[chunk.id] = { range, breaks }
    }
    return out
  })

  return {
    available,
    maps,
    pageMarks,
    scanHighlights,
    textFocus,
    notice,
    currentPageId,
    showTextOnScan,
    showLineInText,
    onScanPage,
    isOwnPageChange,
    cancel
  }
}

export type TextScanSync = ReturnType<typeof useTextScanSync>
