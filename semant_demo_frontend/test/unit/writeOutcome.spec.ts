import { describe, expect, it } from 'vitest'
import { WriteOutcome } from 'src/generated/api'
import { IncompleteWriteError, describeIncomplete, requireComplete } from 'src/utils/writeOutcome'

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
})
