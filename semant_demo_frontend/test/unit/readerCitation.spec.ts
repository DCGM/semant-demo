import { afterEach, describe, expect, it } from 'vitest'

import { citeInReader, clearReaderCitation, requestedCitation } from 'src/features/documents/readerCitation'

afterEach(clearReaderCitation)

describe('citeInReader', () => {
  it('scopes requests and re-triggers on a second click of the same citation', () => {
    citeInReader('chunk-a', 3, 'document-1', 'collection-1')
    const firstToken = requestedCitation.value?.token
    citeInReader('chunk-a', 3, 'document-1', 'collection-1')

    expect(requestedCitation.value).toMatchObject({
      documentId: 'document-1', collectionId: 'collection-1', chunkId: 'chunk-a', order: 3
    })
    expect(requestedCitation.value?.token).not.toBe(firstToken)
  })

  it('can clear the request without retaining a stale chunk', () => {
    citeInReader('chunk-b', null, 'document-2', null)
    clearReaderCitation()
    expect(requestedCitation.value).toBeNull()
  })
})
