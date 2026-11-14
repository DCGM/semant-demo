import { describe, expect, it } from 'vitest'

import { citeInReader, requestedCitation } from 'src/features/documents/readerCitation'

describe('citeInReader', () => {
  it('bumps the request, so the same citation clicked twice still re-triggers, and carries the order', () => {
    citeInReader('chunk-a', 3)
    const firstToken = requestedCitation.value?.token
    citeInReader('chunk-a', 3)

    expect(requestedCitation.value).toMatchObject({ chunkId: 'chunk-a', order: 3 })
    expect(requestedCitation.value?.token).not.toBe(firstToken)
  })
})
