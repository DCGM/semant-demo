import { shallowRef, watch } from 'vue'
import type { CollectionChunk, DocumentPage } from 'src/generated/api'
import { useApi } from 'src/shared/api'
import { readPageChunks } from '../correspondence/pageChunks'
import { useTextScanSync, type TextScanSyncOptions } from '../correspondence/useTextScanSync'
import { createLayoutCache } from '../scan/pageAssets'
import type { useChunkWindow } from './useChunkWindow'

// The text/scan correspondence (#544) in the collection's document reader (#545). The text is
// the reader's own (`useChunkWindow`: the collection's chunks and previews); a page of the
// scan is found in it by reading the page's chunks (public, bounded: correspondence/
// pageChunks.ts) and showing just their orders in the reader (`showRange`), with their
// annotations, never the text between them and what was shown.

export interface ReaderScanSyncOptions {
  documentId: () => string
  chunkWindow: ReturnType<typeof useChunkWindow>
  /** Reads the annotations of chunks newly shown. */
  loadSpans: (chunkIds: string[]) => Promise<void>
  focusScan: TextScanSyncOptions<CollectionChunk>['focusScan']
  revealText: TextScanSyncOptions<CollectionChunk>['revealText']
}

export function useReaderScanSync (o: ReaderScanSyncOptions) {
  const api = useApi().default
  const pages = shallowRef<DocumentPage[]>([])
  const layouts = shallowRef(createLayoutCache())
  const pageReads = new Map<number, Promise<{ chunks: CollectionChunk[], complete: boolean }>>()

  watch(o.documentId, () => {
    pages.value = []
    layouts.value = createLayoutCache()
    pageReads.clear()
  })

  async function readPage (order: number): Promise<{ chunks: CollectionChunk[], complete: boolean }> {
    const documentId = o.documentId()
    const read = await readPageChunks(api, documentId, order)
    if (!read.chunks.length || documentId !== o.documentId()) return { chunks: [], complete: read.complete }
    const orders = read.chunks.map(c => c.order)
    const { shown, fresh } = await o.chunkWindow.showRange(Math.min(...orders), Math.max(...orders))
    if (fresh.length) await o.loadSpans(fresh.map(c => c.id))
    return { chunks: shown.filter(c => c.fromPage <= order && order <= c.toPage), complete: read.complete }
  }

  /** The reader's chunks of page `order`, shown first; once per page (a failed read is tried again). */
  function pageChunks (order: number) {
    let pending = pageReads.get(order)
    if (!pending) {
      pending = readPage(order)
      pending.catch(() => { if (pageReads.get(order) === pending) pageReads.delete(order) })
      pageReads.set(order, pending)
    }
    return pending
  }

  const sync = useTextScanSync({
    pages,
    layouts: () => layouts.value,
    chunks: o.chunkWindow.displayChunks,
    pageChunks,
    focusScan: o.focusScan,
    revealText: o.revealText
  })

  return { pages, layouts, sync }
}
