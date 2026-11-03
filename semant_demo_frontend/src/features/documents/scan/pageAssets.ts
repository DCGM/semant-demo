// Reads of a document's pages (#541): the manifest through the generated client, layout
// files by the URLs it lists (they are JSON files, not API operations), and image URLs for
// <img>. Clients use only the manifest's URLs, so the storage can change behind them.

import type { DocumentPage, DocumentPages } from 'src/generated/api'
import { API_CREDENTIALS, BACKEND_URL, useApi } from 'src/shared/api'
import { apiErrorFromResponse } from 'src/shared/api/errors'
import { parsePageLayout, type PageLayout } from './pageLayout'

/** Absolute URL of an asset URL of the manifest (`/api/documents/...`). */
export function assetUrl (url: string): string {
  return /^[a-z][a-z0-9+.-]*:/i.test(url) ? url : `${BACKEND_URL}${url.startsWith('/') ? '' : '/'}${url}`
}

export function readDocumentPages (documentId: string, signal?: AbortSignal): Promise<DocumentPages> {
  return useApi().default.readDocumentPagesApiDocumentsDocumentIdPagesGet({ documentId }, { signal })
}

async function fetchLayout (page: DocumentPage, signal?: AbortSignal): Promise<PageLayout> {
  if (!page.layoutUrl) throw new Error('The page has no layout')
  // Public corpus data: no token; the backend revalidates layout files (ETag).
  const response = await fetch(assetUrl(page.layoutUrl), { credentials: API_CREDENTIALS, signal })
  if (!response.ok) throw await apiErrorFromResponse(response)
  return parsePageLayout(await response.json(), page.pageId)
}

/** Parsed layouts kept per document view; the least recently used go first. */
export const LAYOUT_CACHE_SIZE = 24

/**
 * A bounded cache of page layouts with one request per page at a time. A request whose
 * every caller has gone (signal aborted) is aborted itself, so paging quickly through a
 * document leaves no obsolete downloads running.
 */
export function createLayoutCache (load: typeof fetchLayout = fetchLayout, size = LAYOUT_CACHE_SIZE) {
  const done = new Map<string, PageLayout>()
  const pending = new Map<string, { promise: Promise<PageLayout>, controller: AbortController, waiting: number }>()

  function remember (pageId: string, layout: PageLayout) {
    done.delete(pageId)
    done.set(pageId, layout)
    while (done.size > size) done.delete(done.keys().next().value as string)
  }

  function get (page: DocumentPage, signal?: AbortSignal): Promise<PageLayout> {
    const cached = done.get(page.pageId)
    if (cached) {
      remember(page.pageId, cached)
      return Promise.resolve(cached)
    }
    let entry = pending.get(page.pageId)
    if (!entry) {
      const controller = new AbortController()
      const promise = load(page, controller.signal).then(layout => {
        remember(page.pageId, layout)
        return layout
      }).finally(() => {
        if (pending.get(page.pageId)?.controller === controller) pending.delete(page.pageId)
      })
      entry = { promise, controller, waiting: 0 }
      pending.set(page.pageId, entry)
    }
    const current = entry
    current.waiting++
    return new Promise<PageLayout>((resolve, reject) => {
      const leave = () => {
        current.waiting--
        if (current.waiting === 0) {
          current.controller.abort()
          if (pending.get(page.pageId) === current) pending.delete(page.pageId)
        }
        reject(new DOMException('Aborted', 'AbortError'))
      }
      if (signal?.aborted) {
        leave()
        return
      }
      signal?.addEventListener('abort', leave, { once: true })
      current.promise.then(
        layout => { signal?.removeEventListener('abort', leave); current.waiting--; resolve(layout) },
        error => { signal?.removeEventListener('abort', leave); current.waiting--; reject(error) }
      )
    })
  }

  return { get, peek: (pageId: string) => done.get(pageId) ?? null, get size () { return done.size } }
}

export type LayoutCache = ReturnType<typeof createLayoutCache>
