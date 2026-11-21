import { describe, expect, it, vi } from 'vitest'

import { confirmBulkDeletion, describeBulkResolve, runBulkResolve } from 'src/features/annotations/bulkResolve'
import { type BulkUpdateSpansResponse, WriteOutcome } from 'src/generated/api'

// Approving or rejecting a large AI selection (#464) runs in bounded, sequential batches.

const ids = Array.from({ length: 1255 }, (_, i) => `s${i}`)

const saved = (batch: string[], failed: BulkUpdateSpansResponse['failed'] = []): BulkUpdateSpansResponse => {
  // A best-effort step after the span write (its vector) does not make the span unsaved.
  const notSaved = new Set(failed.filter((f) => f.step !== 'embed_annotation').map((f) => f.itemId))
  const succeeded = batch.filter((id) => !notSaved.has(id))
  return {
    outcome: failed.length ? (succeeded.length ? WriteOutcome.partial : WriteOutcome.failed) : WriteOutcome.complete,
    succeeded,
    failed,
    unattempted: [],
    spans: [],
    conflicts: []
  }
}

describe('bulk resolving suggestions (#464)', () => {
  it('sends 1,255 ids in bounded batches, one at a time, and reports progress after each', async () => {
    let running = 0
    let peak = 0
    const sizes: number[] = []
    const send = vi.fn(async (batch: string[]) => {
      running++
      peak = Math.max(peak, running)
      sizes.push(batch.length)
      await Promise.resolve()
      running--
      return saved(batch)
    })
    const progress = vi.fn()

    const summary = await runBulkResolve([...ids, ids[0]!], send, progress)

    expect(peak).toBe(1)
    expect(sizes).toEqual([...Array(12).fill(100), 55])
    expect(progress).toHaveBeenCalledTimes(13)
    expect(progress).toHaveBeenLastCalledWith({ total: 1255, processed: 1255, saved: 1255, notSaved: 0 })
    expect(summary.unresolved).toEqual([])
    expect(describeBulkResolve(summary, 'Confirmed')).toBeNull()
  })

  it('keeps failed, uncertain and unsent ids unresolved', async () => {
    const send = vi.fn(async (batch: string[]) => {
      if (batch[0] === 's200') throw new Error('network down')
      if (batch[0] === 's0') {
        return saved(batch, [
          { itemId: 's1', step: 'update_span', message: 'ConnectTimeout', uncertain: true },
          { itemId: 's2', step: 'update_span', message: 'boom' }
        ])
      }
      return saved(batch)
    })

    const summary = await runBulkResolve(ids, send)

    expect(send).toHaveBeenCalledTimes(3)
    expect(summary.saved).toBe(198)
    expect(summary.uncertain).toBe(1)
    expect(summary.unresolved).toEqual(['s1', 's2', ...ids.slice(200)])
    expect(describeBulkResolve(summary, 'Confirmed')).toBe(
      'Confirmed 198 of 1255 suggestions; 1057 not saved and still selected (1 may have been saved; retrying is safe); ' +
      'the remaining requests were stopped after an error. ' +
      'Retry to process the remaining ones.')
  })

  it('counts a saved span whose later best-effort step failed as saved, with nothing to retry', async () => {
    const send = vi.fn(async (batch: string[]) => saved(batch, batch[0] === 's0'
      ? [{ itemId: 's0', step: 'embed_annotation', message: 'provider down', uncertain: true }]
      : []))

    const summary = await runBulkResolve(ids, send)

    expect(summary.saved).toBe(1255)
    expect([summary.unresolved, summary.uncertain]).toEqual([[], 0])
    expect(describeBulkResolve(summary, 'Rejected')).toBeNull()
  })

  it('stops without reporting when the document or collection changed', async () => {
    const send = vi.fn(async (batch: string[]) => batch[0] === 's0' ? saved(batch) : null)

    const summary = await runBulkResolve(ids, send)

    expect(send).toHaveBeenCalledTimes(2)
    expect(summary.abandoned).toBe(true)
    expect(summary.saved).toBe(100)
  })
})

describe('bulk deletion of selected suggestions (#801)', () => {
  it('asks for confirmation for all or large selections', () => {
    expect(confirmBulkDeletion(1, 20)).toBe(false)
    expect(confirmBulkDeletion(1, 1)).toBe(true)
    expect(confirmBulkDeletion(19, 100)).toBe(false)
    expect(confirmBulkDeletion(20, 100)).toBe(true)
  })

  it('reuses the batched progress and keeps only unsuccessful IDs for retry', async () => {
    const result = await runBulkResolve(['one', 'two', 'three'], async () => ({
      succeeded: ['one', 'three'],
      failed: [{ itemId: 'two', step: 'check_type', message: 'already reviewed' }]
    }))
    expect(result.saved).toBe(2)
    expect(result.unresolved).toEqual(['two'])
    expect(describeBulkResolve(result, 'Deleted')).toContain('1 not deleted and still selected')
  })
})

describe('finding the text segments a span overlaps (#464)', () => {
  it('finds the first segment ending after an offset', async () => {
    const { firstSegmentEndingAfter } = await import('src/features/documents/viewer/useReaderGutters')
    const segments = [{ end: 3 }, { end: 7 }, { end: 10 }]

    expect([0, 2, 3, 6, 7, 9, 10, 11].map((o) => firstSegmentEndingAfter(segments, o))).toEqual([0, 0, 1, 1, 2, 2, 3, 3])
    expect(firstSegmentEndingAfter([], 0)).toBe(0)
  })
})
