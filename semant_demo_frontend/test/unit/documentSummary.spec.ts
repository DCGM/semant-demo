import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ResponseError } from 'src/generated/api'
import type { DocumentSummaryCitation, DocumentSummaryResponse } from 'src/generated/api'
import { parseDocumentSummaryTokens, useDocumentSummary } from 'src/features/documents/useDocumentSummary'

interface PendingCall {
  collectionId: string
  documentId: string
  length?: string
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
          requestParameters: { collectionId: string, documentId: string, length?: string },
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

const response = (
  summary: string, citations: DocumentSummaryCitation[], overrides: Partial<DocumentSummaryResponse> = {}
): DocumentSummaryResponse => ({
  documentId: 'd1',
  summary,
  citations,
  timeSpent: 1.5,
  totalChunks: citations.length,
  summarizedChunks: citations.length,
  truncated: false,
  ...overrides
})

describe('parseDocumentSummaryTokens', () => {
  it('maps a [docN] citation to the Nth citation (1-based), not a renumbered index', () => {
    const citations = [citation('chunk-a', 0), citation('chunk-b', 1)]
    const tokens = parseDocumentSummaryTokens('Text [doc2] more [doc1].', citations)

    expect(tokens).toEqual([
      { type: 'text', value: 'Text ' },
      { type: 'citation', chunkId: 'chunk-b', number: 2, order: 1 },
      { type: 'text', value: ' more ' },
      { type: 'citation', chunkId: 'chunk-a', number: 1, order: 0 },
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
    // The composable is a module-scope singleton: start clean.
    useDocumentSummary().setLength('short')
    useDocumentSummary().reset()
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
      { type: 'citation', chunkId: 'chunk-a', number: 1, order: 0 },
      { type: 'text', value: '.' }
    ])
    expect(summary.timeSpent.value).toBe(1.5)
    expect(summary.error.value).toBeNull()
    expect([summary.totalChunks.value, summary.summarizedChunks.value, summary.truncated.value]).toEqual([1, 1, false])
  })

  it('sends the chosen length level, short by default', async () => {
    const summary = useDocumentSummary()
    expect(summary.length.value).toBe('short')

    summary.setLength('detailed')
    const request = summary.summarize('c1', 'd1')
    expect(calls[0].length).toBe('detailed')
    calls[0].resolve(response('Podrobné shrnutí [doc1].', [citation('chunk-a', 0)]))
    await request

    expect([summary.length.value, summary.summary.value]).toEqual(['detailed', 'Podrobné shrnutí [doc1].'])
  })

  it('a new length level drops a running request and clears a shown summary', async () => {
    const summary = useDocumentSummary()
    const running = summary.summarize('c1', 'd1')

    summary.setLength('detailed') // chosen before the short summary arrives
    expect(calls[0].signal?.aborted).toBe(true)
    await running
    expect([summary.summary.value, summary.summarizing.value, summary.error.value]).toEqual(['', false, null])

    const second = summary.summarize('c1', 'd1')
    calls[1].resolve(response('Shrnutí [doc1].', [citation('chunk-a', 0)]))
    await second
    summary.setLength('detailed') // the same level again keeps the summary
    expect(summary.summary.value).toBe('Shrnutí [doc1].')

    summary.setLength('short')
    expect(summary.summary.value).toBe('')
  })

  it('exposes a truncation notice for a partial summary', async () => {
    const summary = useDocumentSummary()

    const request = summary.summarize('c1', 'd1')
    calls[0].resolve(response('Shrnutí [doc1].', [citation('chunk-a', 0)], { totalChunks: 500, summarizedChunks: 1, truncated: true }))
    await request

    expect([summary.totalChunks.value, summary.summarizedChunks.value, summary.truncated.value]).toEqual([500, 1, true])
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

  it('a plain network failure sets a generic error, not the raw exception', async () => {
    const summary = useDocumentSummary()

    const request = summary.summarize('c1', 'd1')
    calls[0].reject(new Error('network exploded'))
    await request

    expect(summary.summarizing.value).toBe(false)
    expect(summary.error.value).toBe('Failed to summarize the document.')
  })

  it('a backend generation failure (502) shows its safe detail message, not a generic one', async () => {
    const summary = useDocumentSummary()
    const backendResponse = new Response(JSON.stringify({ detail: 'The document could not be summarized.' }), { status: 502 })

    const request = summary.summarize('c1', 'd1')
    calls[0].reject(new ResponseError(backendResponse))
    await request

    expect(summary.summarizing.value).toBe(false)
    expect(summary.error.value).toBe('The document could not be summarized.')
  })

  it('a refusal for the daily AI allowance (429) explains it instead of the backend detail', async () => {
    const summary = useDocumentSummary()
    const refusal = {
      detail: 'Insufficient remaining daily AI allowance for this operation; it resets at 2026-10-18 00:00 UTC.',
      code: 'llm_quota_exhausted',
      principal: 'guest',
      reset_at: '2026-10-18T00:00:00Z',
      limit_usd: 0.25,
      used_usd: 0.25
    }

    const request = summary.summarize('c1', 'd1')
    calls[0].reject(new ResponseError(new Response(JSON.stringify(refusal), { status: 429 })))
    await request

    expect(summary.error.value).toMatch(/^Today's AI allowance has no room for this request, so nothing was generated\. It resets /)
    expect(summary.error.value).toContain('Logging in gives you a separate daily allowance.')
    expect([calls.length, summary.summarizing.value]).toEqual([1, false])
  })

  it('cite() bumps requestedCitation so clicking the same citation twice still re-triggers, and carries the order', () => {
    const summary = useDocumentSummary()

    summary.cite('chunk-a', 3)
    const firstToken = summary.requestedCitation.value?.token
    summary.cite('chunk-a', 3)

    expect(summary.requestedCitation.value).toMatchObject({ chunkId: 'chunk-a', order: 3 })
    expect(summary.requestedCitation.value?.token).not.toBe(firstToken)
  })
})
