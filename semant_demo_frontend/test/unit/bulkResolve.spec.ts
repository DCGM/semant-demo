import { describe, expect, it, vi } from 'vitest'

import { describeBulkResolve, runBulkResolve } from 'src/features/annotations/bulkResolve'
import { type BulkUpdateSpansResponse, WriteOutcome } from 'src/generated/api'

// Approving or rejecting a large AI selection (#464) runs in bounded, sequential batches.

const ids = Array.from({ length: 1255 }, (_, i) => `s${i}`)

const saved = (batch: string[], failed: BulkUpdateSpansResponse['failed'] = []): BulkUpdateSpansResponse => {
  const notSaved = new Set(failed.filter((f) => f.step !== 'update_chunk_tags').map((f) => f.itemId))
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

  it('keeps failed, uncertain and unsent ids unresolved and tells stale search apart', async () => {
    const send = vi.fn(async (batch: string[]) => {
      if (batch[0] === 's200') throw new Error('network down')
      if (batch[0] === 's0') {
        return saved(batch, [
          { itemId: 's1', step: 'update_span', message: 'ConnectTimeout', uncertain: true },
          { itemId: 's2', step: 'update_span', message: 'boom' },
          { itemId: 's3', step: 'update_chunk_tags', message: 'sync failed' }
        ])
      }
      return saved(batch)
    })

    const summary = await runBulkResolve(ids, send)

    expect(send).toHaveBeenCalledTimes(3)
    expect(summary.saved).toBe(198)
    expect(summary.staleSearch).toBe(1)
    expect(summary.uncertain).toBe(1)
    expect(summary.unresolved).toEqual(['s1', 's2', ...ids.slice(200)])
    expect(describeBulkResolve(summary, 'Confirmed')).toBe(
      'Confirmed 198 of 1255 suggestions; 1057 not saved and still selected (1 may have been saved; retrying is safe); ' +
      '1 saved, but tag search may not show them yet; the remaining requests were stopped after an error. ' +
      'Retry to process the remaining ones.')
  })

  it('stops without reporting when the document or collection changed', async () => {
    const send = vi.fn(async (batch: string[]) => batch[0] === 's0' ? saved(batch) : null)

    const summary = await runBulkResolve(ids, send)

    expect(send).toHaveBeenCalledTimes(2)
    expect(summary.abandoned).toBe(true)
    expect(summary.saved).toBe(100)
  })
})
