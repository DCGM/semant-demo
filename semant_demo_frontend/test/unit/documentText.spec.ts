import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { DocumentChunk } from 'src/generated/api'

// The bounded text reads of the paired view (#544): a page with more chunks than one
// `/chunks/by_page` read returns is continued with `/adjacent`, a bounded number of times,
// and says when chunks of the page may remain unread.

const PAGE = 7
let chunks: DocumentChunk[] = []
const calls: string[] = []

const chunk = (order: number, fromPage: number, toPage = fromPage): DocumentChunk => ({
  id: `c${order}`, order, fromPage, toPage, text: `chunk ${order}`, startPageId: 'p', document: 'd'
})

vi.mock('src/shared/api', async () => {
  const actual = await vi.importActual<typeof import('src/shared/api')>('src/shared/api')
  return {
    ...actual,
    useApi: () => ({
      default: {
        readDocumentPageChunksApiDocumentsDocumentIdChunksByPageGet: ({ page, limit }: { page: number, limit: number }) => {
          calls.push(`by_page ${page} ${limit}`)
          const covering = chunks.filter(c => c.fromPage <= page && page <= c.toPage)
          return Promise.resolve({ page, chunks: covering.slice(0, limit), hasMore: covering.length > limit })
        },
        readDocumentAdjacentChunksApiDocumentsDocumentIdChunksChunkIdAdjacentGet: ({ chunkId, limit }: { chunkId: string, limit: number }) => {
          calls.push(`adjacent ${chunkId} ${limit}`)
          const i = chunks.findIndex(c => c.id === chunkId)
          return Promise.resolve({ chunks: chunks.slice(i + 1, i + 1 + limit) })
        }
      }
    })
  }
})

const { useDocumentText } = await import('src/features/documents/correspondence/useDocumentText')

beforeEach(() => {
  calls.length = 0
})

describe('useDocumentText page reads', () => {
  it('reads every chunk of a page with more than one read returns, and only that page', async () => {
    // 2 chunks before the page, 120 on it, then the next pages.
    chunks = [chunk(0, 5), chunk(1, 6, PAGE), ...Array.from({ length: 119 }, (_, i) => chunk(i + 2, PAGE)), chunk(121, PAGE, 8), chunk(122, 8), ...Array.from({ length: 60 }, (_, i) => chunk(i + 123, 9))]
    const text = useDocumentText(() => 'd')
    const read = await text.pageChunks(PAGE)
    expect(read.complete).toBe(true)
    expect(read.chunks.map(c => c.order)).toEqual(Array.from({ length: 121 }, (_, i) => i + 1))
    expect(text.chunks.value).toHaveLength(121)
    expect(calls).toEqual(['by_page 7 50', 'adjacent c50 50', 'adjacent c100 50'])
    // Read once per page.
    await text.pageChunks(PAGE)
    expect(calls).toHaveLength(3)
  })

  it('stops after a few further reads and says the page may have more', async () => {
    chunks = Array.from({ length: 400 }, (_, i) => chunk(i, PAGE))
    const text = useDocumentText(() => 'd')
    const read = await text.pageChunks(PAGE)
    expect(read.complete).toBe(false)
    expect(read.chunks).toHaveLength(200)
    expect(calls).toHaveLength(4)
  })

  it('is complete without further reads when one read has them all', async () => {
    chunks = [chunk(0, PAGE), chunk(1, PAGE + 1)]
    const read = await useDocumentText(() => 'd').pageChunks(PAGE)
    expect(read).toMatchObject({ complete: true, failed: false })
    expect(read.chunks.map(c => c.id)).toEqual(['c0'])
    expect(calls).toEqual(['by_page 7 50'])
  })
})
