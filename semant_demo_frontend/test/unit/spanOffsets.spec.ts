import { describe, expect, it } from 'vitest'
import { anchorAtStart, offsetBetween, projectSpan } from 'src/features/annotations/spanOffsets'
import fixture from '../../../semant_demo_backend/tests/fixtures/text_offsets.json'

// Cases shared with the backend (tests/test_span_offsets.py). The backend also rejects
// the spans with an `error`; the frontend only projects them.
describe('span offsets', () => {
  for (const c of fixture.cases) {
    it(`projects: ${c.name}`, () => {
      expect(projectSpan(c.chunks, c.anchor, c.start, c.end)).toEqual(c.parts)
    })
  }

  it('measures text in UTF-16 code units', () => {
    expect(offsetBetween([{ order: 0, text: 'x😀' }, { order: 1, text: 'y' }], 0, 1)).toBe(3)
  })

  it('has no offset across a gap or backwards', () => {
    const chunks = [{ order: 0, text: 'abc' }, { order: 2, text: 'def' }]
    expect(offsetBetween(chunks, 0, 1)).toBeNull()
    expect(offsetBetween(chunks, 1, 0)).toBeNull()
  })

  it('anchors a range on the chunk where it starts, only across consecutive chunks', () => {
    const chunks = [{ order: 0, text: 'abc' }, { order: 1, text: 'de' }, { order: 3, text: 'fgh' }]
    // A start dragged before or after its chunk moves the anchor there.
    expect(anchorAtStart(chunks, 1, -2, 1)).toEqual({ index: 0, start: 1, end: 4 })
    expect(anchorAtStart(chunks, 0, 4, 6)).toEqual({ index: 1, start: 1, end: 3 })
    // Not across the gap between orders 1 and 3, and never empty.
    expect(anchorAtStart(chunks, 1, 2, 4)).toBeNull()
    expect(anchorAtStart(chunks, 2, -1, 2)).toBeNull()
    expect(anchorAtStart(chunks, 0, 1, 1)).toBeNull()
  })
})
