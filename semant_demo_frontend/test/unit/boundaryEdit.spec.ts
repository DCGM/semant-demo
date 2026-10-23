import { describe, expect, it } from 'vitest'
import type { DocumentChunk } from 'src/generated/api'
import { rangeBetween, rangeText, stepBoundary } from 'src/features/annotations/concordance/boundaryEdit'

// Boundary editing in the workspace's source passage (#461): ranges stay anchored on the
// chunk where they start, as in the document view (a start moved into the previous chunk
// moves the annotation there, #436), within the loaded chunks of consecutive order.

const chunk = (id: string, order: number | null, text: string) => ({ id, order, text }) as DocumentChunk
const chunks = [chunk('c1', 4, 'Jan Novák '), chunk('c2', 5, 'žil v Brně 😀 dlouho.'), chunk('c4', 7, 'Jinde.')]
// "v Brně" in c2.
const brne = { chunkId: 'c2', start: 4, end: 10 }

describe('boundary editing', () => {
  it('moves either boundary by words', () => {
    expect(rangeText(chunks, brne)).toBe('v Brně')
    const later = stepBoundary(chunks, brne, 'end', 1, 'word')
    expect(later && rangeText(chunks, later)).toBe('v Brně 😀')
    const shorter = stepBoundary(chunks, brne, 'start', 1, 'word')
    expect(shorter).toEqual({ chunkId: 'c2', start: 6, end: 10 })
    expect(stepBoundary(chunks, brne, 'end', -1, 'word')).toEqual({ chunkId: 'c2', start: 4, end: 5 })
  })

  it('moves the anchor to the previous chunk when the start moves into it', () => {
    const word = stepBoundary(chunks, { chunkId: 'c2', start: 0, end: 3 }, 'start', -1, 'word')
    expect(word).toEqual({ chunkId: 'c1', start: 4, end: 13 })
    expect(word && rangeText(chunks, word)).toBe('Novák žil')
    // And back again by characters.
    let range = word
    for (let i = 0; i < 6 && range; i++) range = stepBoundary(chunks, range, 'start', 1, 'character')
    expect(range).toEqual({ chunkId: 'c2', start: 0, end: 3 })
  })

  it('steps over a surrogate pair at once', () => {
    const emoji = { chunkId: 'c2', start: 11, end: 13 }
    expect(rangeText(chunks, emoji)).toBe('😀')
    expect(stepBoundary(chunks, emoji, 'end', -1, 'character')).toBeNull()
    expect(stepBoundary(chunks, { chunkId: 'c2', start: 10, end: 13 }, 'start', 1, 'character')).toEqual(emoji)
  })

  it('keeps the start before the end and both within the consecutive loaded text', () => {
    expect(stepBoundary(chunks, { chunkId: 'c2', start: 4, end: 5 }, 'start', 1, 'character')).toBeNull()
    expect(stepBoundary(chunks, { chunkId: 'c1', start: 0, end: 3 }, 'start', -1, 'word')).toBeNull()
    // c4 follows a gap: the end of c2 is the end of the text an annotation there can reach.
    expect(stepBoundary(chunks, { chunkId: 'c2', start: 14, end: 21 }, 'end', 1, 'word')).toBeNull()
    expect(stepBoundary(chunks, brne, 'start', 1, 'word')).not.toBeNull()
    expect(stepBoundary(chunks, { chunkId: 'gone', start: 0, end: 1 }, 'end', 1, 'word')).toBeNull()
  })

  it('takes a text selection in either direction, across consecutive chunks only', () => {
    expect(rangeBetween(chunks, { chunkId: 'c2', offset: 3 }, { chunkId: 'c1', offset: 4 }))
      .toEqual({ chunkId: 'c1', start: 4, end: 13 })
    expect(rangeBetween(chunks, { chunkId: 'c2', offset: 0 }, { chunkId: 'c4', offset: 2 })).toBeNull()
    expect(rangeBetween(chunks, { chunkId: 'c2', offset: 2 }, { chunkId: 'c2', offset: 2 })).toBeNull()
    // A selection ending exactly at the end of a chunk starts nowhere past it.
    expect(rangeBetween(chunks, { chunkId: 'c1', offset: 10 }, { chunkId: 'c2', offset: 3 }))
      .toEqual({ chunkId: 'c2', start: 0, end: 3 })
  })
})
