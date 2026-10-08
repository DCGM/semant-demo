import { describe, expect, it } from 'vitest'
import { SpanType, WriteOutcome } from 'src/generated/api'
import { IncompleteWriteError, describeIncomplete, incompleteWriteMessage, requireComplete, searchTagWarning, spanOf } from 'src/utils/writeOutcome'

describe('write outcomes', () => {
  it('passes complete results through', () => {
    const result = { outcome: WriteOutcome.complete, succeeded: ['a'] }
    expect(requireComplete(result, 'Adding the document')).toBe(result)
  })

  it('rejects partial results with a message naming failed and uncertain steps', () => {
    const result = {
      outcome: WriteOutcome.partial,
      succeeded: ['a'],
      failed: [
        { itemId: 'b', step: 'link_chunk', message: 'x', uncertain: true },
        { itemId: 'c', step: 'link_chunk', message: 'x', uncertain: false }
      ],
      unattempted: ['doc']
    }

    expect(() => requireComplete(result, 'Adding the document')).toThrow(IncompleteWriteError)
    expect(describeIncomplete(result, 'Adding the document')).toBe(
      'Adding the document was only partly completed; 2 step(s) failed (1 may still have been applied); ' +
      '1 not attempted. Completed changes were kept; you can retry.'
    )
  })

  it('describes total failure', () => {
    expect(describeIncomplete({ outcome: WriteOutcome.failed, failed: [] }, 'Removing the document'))
      .toMatch(/^Removing the document failed\./)
  })

  it('warns about a span write whose search tag update failed', () => {
    const failed = [{ itemId: 'chunk:tag', step: 'update_chunk_tags', message: 'x', uncertain: false }]
    expect(searchTagWarning({ outcome: WriteOutcome.complete, succeeded: ['s'] }, 'saved')).toBeNull()
    expect(searchTagWarning({ outcome: WriteOutcome.partial, succeeded: ['s'], failed }, 'saved'))
      .toMatch(/saved, but tag search was not updated/)
    expect(searchTagWarning({ outcome: WriteOutcome.partial, succeeded: ['s'], failed }, 'deleted'))
      .toMatch(/deleted, but tag search may still find/)
  })

  it('keeps only the span fields of a span write result', () => {
    const span = { id: 's', chunkId: 'c', tagId: 't', start: 1, end: 4, type: SpanType.pos, reason: null, confidence: null }
    expect(spanOf({ ...span, outcome: WriteOutcome.complete, succeeded: ['s'], failed: [], unattempted: [] }))
      .toEqual(span)
  })

  it('shows the message of a write that stopped part way', async () => {
    const body = { detail: 'Deleting the tag stopped at step delete_span.', step: 'delete_span', completed: {}, uncertain: false }
    const stopped = { response: new Response(JSON.stringify(body), { status: 500 }) }
    expect(await incompleteWriteMessage(stopped, 'Failed')).toBe(body.detail)
  })

  it('falls back for other errors', async () => {
    expect(await incompleteWriteMessage(new Error('network'), 'Failed')).toBe('Failed')
    expect(await incompleteWriteMessage({ response: new Response('Internal Server Error', { status: 500 }) }, 'Failed')).toBe('Failed')
    expect(await incompleteWriteMessage({ response: new Response('{"detail": "x"}', { status: 404 }) }, 'Failed')).toBe('Failed')
  })
})
