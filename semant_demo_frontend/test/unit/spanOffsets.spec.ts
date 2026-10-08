import { describe, expect, it } from 'vitest'
import { offsetBetween, projectSpan } from 'src/utils/spanOffsets'
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
})
