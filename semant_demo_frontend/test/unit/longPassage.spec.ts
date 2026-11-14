import { describe, expect, it } from 'vitest'

import corpus from '../../../semant_demo_backend/tests/fixtures/corpus.json'
import { LONG_PASSAGE_TERM, LONG_PASSAGE_TEXT, LONG_PASSAGE_TOKEN } from '../fixtures/longPassage'

// The shared long passage (#274) keeps the properties layout tests rely on.
describe('long passage fixture', () => {
  it('is long, multi-paragraph and multilingual', () => {
    expect(LONG_PASSAGE_TEXT.length).toBeGreaterThanOrEqual(800)
    expect(LONG_PASSAGE_TEXT.split('\n\n').length).toBeGreaterThanOrEqual(4)
    expect(LONG_PASSAGE_TEXT).toMatch(/[^\n]\n[^\n]/) // a line break inside a paragraph
    for (const edge of ['ř', 'ß', 'ł', 'é', 'Д', 'λ', '\u{1F4DC}']) expect(LONG_PASSAGE_TEXT).toContain(edge)
  })

  it('has a unique search term and an unbreakable long token', () => {
    expect(LONG_PASSAGE_TEXT).toContain(LONG_PASSAGE_TERM)
    const chunkTexts = corpus.documents.flatMap((d) => d.chunks.map((c) => c.text))
    expect(chunkTexts.filter((text) => text.includes(LONG_PASSAGE_TERM))).toEqual([])
    expect(LONG_PASSAGE_TOKEN.length).toBeGreaterThanOrEqual(100)
    expect(LONG_PASSAGE_TOKEN).not.toMatch(/\s/)
    expect(LONG_PASSAGE_TEXT).toContain(LONG_PASSAGE_TOKEN)
  })

  it('has no surrounding or doubled spaces (tests compare the rendered text exactly)', () => {
    expect(LONG_PASSAGE_TEXT).toBe(LONG_PASSAGE_TEXT.trim())
    expect(LONG_PASSAGE_TEXT).not.toMatch(/ {2}| \n|\n /)
  })
})
