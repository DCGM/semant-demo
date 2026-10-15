import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { DocumentSummaryCitation, DocumentSummaryResponse } from 'src/generated/api'
import { parseDocumentSummaryTokens, useDocumentSummary } from 'src/features/documents/useDocumentSummary'

interface PendingCall {
  collectionId: string
  documentId: string
  signal?: AbortSignal
  resolve: (value: DocumentSummaryResponse) => void
  reject: (error: unknown) => void
}

let calls: PendingCall[]

vi.mock('src/shared/api', async () => {
  const actual = await vi.importActual<typeof import('src/shared/api')>('src/shared/api')
  return {
    ...actual,
    useApi: () => ({
      default: {
        summarizeDocumentApiUserCollectionsCollectionIdDocumentsDocumentIdSummaryPost: (
          requestParameters: { collectionId: string, documentId: string },
          initOverrides?: { signal?: AbortSignal }
        ) => new Promise<DocumentSummaryResponse>((resolve, reject) => {
          const signal = initOverrides?.signal
          const abort = () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' }))
          if (signal?.aborted) abort()
          signal?.addEventListener('abort', abort)
          calls.push({ ...requestParameters, signal, resolve, reject })
        })
      }
    })
  }
})

const citation = (chunkId: string, order: number): DocumentSummaryCitation => ({
  chunkId, order, fromPage: order + 1, toPage: order + 1
})

const response = (summary: string, citations: DocumentSummaryCitation[]): DocumentSummaryResponse => ({
  documentId: 'd1', summary, citations, timeSpent: 1.5
})

describe('parseDocumentSummaryTokens', () => {
  it('maps a [docN] citation to the Nth citation (1-based), not a renumbered index', () => {
    const citations = [citation('chunk-a', 0), citation('chunk-b', 1)]
    const tokens = parseDocumentSummaryTokens('Text [doc2] more [doc1].', citations)

    expect(tokens).toEqual([
      { type: 'text', value: 'Text ' },
      { type: 'citation', chunkId: 'chunk-b', number: 2 },
      { type: 'text', value: ' more ' },
      { type: 'citation', chunkId: 'chunk-a', number: 1 },
      { type: 'text', value: '.' }
    ])
  })

  it('shows a label with no matching citation as plain text rather than a dead link', () => {
    const tokens = parseDocumentSummaryTokens('See [doc3].', [citation('chunk-a', 0)])

    expect(tokens.every((t) => t.type === 'text')).toBe(true)
    expect(tokens.map((t) => (t.type === 'text' ? t.value : '')).join('')).toBe('See [doc3].')
  })
})

describe('useDocumentSummary', () => {
  beforeEach(() => {
    calls = []
    useDocumentSummary().reset() // the composable is a module-scope singleton: start clean
  })

  it('summarizes a document and exposes citations and tokens', async () => {
    const summary = useDocumentSummary()

    const request = summary.summarize('c1', 'd1')
    expect(summary.summarizing.value).toBe(true)
    expect(calls).toHaveLength(1)
    expect([calls[0].collectionId, calls[0].documentId]).toEqual(['c1', 'd1'])

    calls[0].resolve(response('Shrnutí [doc1].', [citation('chunk-a', 0)]))
    await request

    expect(summary.summarizing.value).toBe(false)
    expect(summary.citations.value).toEqual([citation('chunk-a', 0)])
    expect(summary.tokens.value).toEqual([
      { type: 'text', value: 'Shrnutí ' },
      { type: 'citation', chunkId: 'chunk-a', number: 1 },
      { type: 'text', value: '.' }
    ])
    expect(summary.timeSpent.value).toBe(1.5)
    expect(summary.error.value).toBeNull()
  })

  it('a second summarize() call while one is in flight is a no-op (no duplicate request)', async () => {
    const summary = useDocumentSummary()

    const first = summary.summarize('c1', 'd1')
    await summary.summarize('c1', 'd1') // e.g. a double click of the Summarize button
    expect(calls).toHaveLength(1)

    calls[0].resolve(response('Shrnutí [doc1].', [citation('chunk-a', 0)]))
    await first
  })

  it('drops a stale answer once reset() (e.g. a document change) supersedes the request', async () => {
    const summary = useDocumentSummary()

    const first = summary.summarize('c1', 'd1')
    expect(calls).toHaveLength(1)

    // DocumentViewLayout's document/collection watchers call reset() before the page moves on.
    summary.reset()
    const second = summary.summarize('c1', 'd2')
    expect(calls).toHaveLength(2)

    calls[1].resolve(response('Shrnutí d2 [doc1].', [citation('chunk-b', 0)]))
    await second
    expect(summary.citations.value).toEqual([citation('chunk-b', 0)])

    // The first (now stale) request answering afterwards must not overwrite the current state.
    calls[0].resolve(response('Shrnutí d1 [doc1].', [citation('chunk-a', 0)]))
    await first

    expect(summary.citations.value).toEqual([citation('chunk-b', 0)])
    expect(summary.summary.value).toBe('Shrnutí d2 [doc1].')
  })

  it('reset() aborts an in-flight request and ignores its late answer', async () => {
    const summary = useDocumentSummary()

    const request = summary.summarize('c1', 'd1')
    expect(calls[0].signal?.aborted).toBe(false)

    summary.reset()
    expect(calls[0].signal?.aborted).toBe(true)
    expect(summary.summarizing.value).toBe(false)

    calls[0].resolve(response('Late answer [doc1].', [citation('chunk-a', 0)]))
    await request

    expect(summary.summary.value).toBe('')
    expect(summary.citations.value).toEqual([])
    expect(summary.summarizing.value).toBe(false)
  })

  it('cancel() aborts without surfacing the abort as an error', async () => {
    const summary = useDocumentSummary()

    const request = summary.summarize('c1', 'd1')
    summary.cancel()
    calls[0].reject(Object.assign(new Error('aborted'), { name: 'AbortError' }))
    await request

    expect(summary.summarizing.value).toBe(false)
    expect(summary.error.value).toBeNull()
  })

  it('a provider failure sets a generic error, not the raw exception', async () => {
    const summary = useDocumentSummary()

    const request = summary.summarize('c1', 'd1')
    calls[0].reject(new Error('network exploded'))
    await request

    expect(summary.summarizing.value).toBe(false)
    expect(summary.error.value).toBe('Failed to summarize the document.')
  })

  it('cite() bumps requestedCitation so clicking the same citation twice still re-triggers', () => {
    const summary = useDocumentSummary()

    summary.cite('chunk-a')
    const firstToken = summary.requestedCitation.value?.token
    summary.cite('chunk-a')

    expect(summary.requestedCitation.value?.chunkId).toBe('chunk-a')
    expect(summary.requestedCitation.value?.token).not.toBe(firstToken)
  })
})
