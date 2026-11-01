import { describe, expect, it } from 'vitest'
import type { CollectionChunk } from 'src/generated/api'
import {
  assignColumns, gapSize, groupParagraphs, knownChunksInOrder, missingChunksText, rangeByChunk, resolveSelectionEndpoint,
  selectionInDisplayedChunks, selectionText, shortestMarker
} from 'src/features/documents/viewer/readerOffsets'

const chunk = (id: string, order: number, text: string, endParagraph = false) =>
  ({ id, order, text, endParagraph, inCollection: true }) as CollectionChunk

// Orders 0, 1, 2 are consecutive; 4 follows a gap.
const a = chunk('a', 0, 'Hello ')
const b = chunk('b', 1, 'world', true)
const c = chunk('c', 2, 'Again')
const e = chunk('e', 4, 'Later')

describe('groupParagraphs', () => {
  it('ends paragraphs at endParagraph and at gaps, with the orders around each gap', () => {
    expect(groupParagraphs([a, b, c, e])).toEqual([
      { chunks: [a, b], gapAfter: null, gapBefore: null },
      { chunks: [c], gapAfter: 2, gapBefore: 4 },
      { chunks: [e], gapAfter: null, gapBefore: null }
    ])
    expect(groupParagraphs([])).toEqual([])
  })
})

describe('rangeByChunk', () => {
  it('splits a range across consecutive chunks into chunk-local offsets', () => {
    // "Hello " (6) + "world" (5) + "Again" (5)
    expect(rangeByChunk({ chunkId: 'a', start: 4, end: 13 }, [a, b, c, e])).toEqual({
      a: { start: 4, end: 6 }, b: { start: 0, end: 5 }, c: { start: 0, end: 2 }
    })
    expect(rangeByChunk({ chunkId: 'b', start: 1, end: 3 }, [a, b, c])).toEqual({ b: { start: 1, end: 3 } })
  })

  it('stops at a gap in chunk order and ignores an unknown anchor or an empty range', () => {
    expect(rangeByChunk({ chunkId: 'c', start: 2, end: 20 }, [a, b, c, e])).toEqual({ c: { start: 2, end: 5 } })
    expect(rangeByChunk({ chunkId: 'x', start: 0, end: 3 }, [a, b])).toEqual({})
    expect(rangeByChunk({ chunkId: 'a', start: 2, end: 2 }, [a, b])).toEqual({})
  })
})

describe('gap divider', () => {
  it('counts the chunks missing between two paragraphs', () => {
    const [first, second, last] = groupParagraphs([a, b, c, e])
    expect(gapSize(first)).toBe(0)
    expect(gapSize(second)).toBe(1)
    expect(gapSize(last)).toBe(0)
    expect(gapSize({ chunks: [], gapAfter: 3, gapBefore: 7 })).toBe(3)
  })

  it('says how many chunks are not shown', () => {
    expect(missingChunksText(1)).toBe('1 chunk not shown')
    expect(missingChunksText(3)).toBe('3 chunks not shown')
  })
})

describe('shortestMarker', () => {
  const marker = (spanId: string, start: number, end: number, isAuto = false) => ({ spanId, start, end, isAuto })

  it('picks the shortest span', () => {
    expect(shortestMarker([marker('long', 0, 20), marker('short', 5, 9), marker('mid', 2, 12)])?.spanId).toBe('short')
  })

  it('prefers an approved span, then the earlier one, at the same length', () => {
    expect(shortestMarker([marker('ai', 0, 4, true), marker('approved', 3, 7)])?.spanId).toBe('approved')
    expect(shortestMarker([marker('later', 6, 10), marker('earlier', 2, 6)])?.spanId).toBe('earlier')
  })

  it('returns null without markers', () => {
    expect(shortestMarker([])).toBeNull()
  })
})

describe('knownChunksInOrder', () => {
  it('merges displayed and hidden chunks without duplicates in order', () => {
    expect(knownChunksInOrder([c, a], [b, a]).map((x) => x.id)).toEqual(['a', 'b', 'c'])
  })
})

describe('selectionInDisplayedChunks', () => {
  it('keeps a selection within one chunk', () => {
    expect(selectionInDisplayedChunks({ chunkId: 'b', start: 1, end: 4 }, [a, b], []))
      .toEqual({ chunkIds: ['b'], start: 1, end: 4 })
  })

  it('maps a selection across chunks into their concatenated text', () => {
    expect(selectionInDisplayedChunks({ chunkId: 'a', start: 3, end: 8 }, [a, b, c], []))
      .toEqual({ chunkIds: ['a', 'b'], start: 3, end: 8 })
  })

  it('skips a hidden chunk and re-measures the offsets without it', () => {
    // a (0-6) + hidden b (6-11) + c (11-16); the selection ends in c.
    expect(selectionInDisplayedChunks({ chunkId: 'a', start: 2, end: 13 }, [a, c], [b]))
      .toEqual({ chunkIds: ['a', 'c'], start: 2, end: 8 })
  })

  it('stops at a gap and rejects selections outside the displayed chunks', () => {
    expect(selectionInDisplayedChunks({ chunkId: 'c', start: 0, end: 20 }, [c, e], []))
      .toEqual({ chunkIds: ['c'], start: 0, end: 5 })
    expect(selectionInDisplayedChunks({ chunkId: 'b', start: 0, end: 3 }, [a], [b])).toBeNull()
    expect(selectionInDisplayedChunks({ chunkId: 'x', start: 0, end: 3 }, [a], [])).toBeNull()
  })
})

describe('selectionText', () => {
  it('returns the text of a selection, also across chunks', () => {
    expect(selectionText({ chunkId: 'b', start: 0, end: 5 }, [a, b])).toBe('world')
    expect(selectionText({ chunkId: 'a', start: 3, end: 8 }, [b, a])).toBe('lo wo')
  })

  it('clips offsets beyond the known text', () => {
    expect(selectionText({ chunkId: 'c', start: 2, end: 99 }, [c])).toBe('ain')
    expect(selectionText({ chunkId: 'x', start: 0, end: 3 }, [a])).toBe('')
  })
})

describe('assignColumns', () => {
  it('puts overlapping markers side by side, longer ones nearer the text, and reuses free columns', () => {
    const items = [
      { id: 3, top: 60, height: 20, column: 0 },
      { id: 1, top: 0, height: 50, column: 0 },
      { id: 2, top: 10, height: 20, column: 0 },
      { id: 4, top: 52, height: 20, column: 0 } // 2 px below marker 1: too close
    ]
    expect(assignColumns(items).map((i) => [i.id, i.column])).toEqual([[1, 0], [2, 1], [4, 1], [3, 0]])
  })
})

describe('resolveSelectionEndpoint', () => {
  it('resolves a text node offset to its chunk offset through the segment start', () => {
    document.body.innerHTML =
      '<div data-chunk-id="a"><span class="text-segment" data-start="5" data-end="9">text</span></div><p>outside</p>'
    const text = document.querySelector('.text-segment')!.firstChild!
    expect(resolveSelectionEndpoint(text, 2)).toEqual({ chunkId: 'a', charOffset: 7 })
    expect(resolveSelectionEndpoint(document.querySelector('.text-segment')!, 1)).toEqual({ chunkId: 'a', charOffset: 5 })
    expect(resolveSelectionEndpoint(document.querySelector('p')!.firstChild!, 1)).toBeNull()
  })
})
