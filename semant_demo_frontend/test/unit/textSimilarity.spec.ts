import { describe, expect, it } from 'vitest'
import { levenshtein, similarity } from 'src/shared/textSimilarity'

describe('levenshtein', () => {
  it('is 0 for identical strings and the length for an empty one', () => {
    expect(levenshtein('abc', 'abc')).toBe(0)
    expect(levenshtein('', 'abc')).toBe(3)
    expect(levenshtein('abc', '')).toBe(3)
  })

  it('counts the minimum single-character edits', () => {
    expect(levenshtein('kitten', 'sitting')).toBe(3)
    expect(levenshtein('Novak', 'Novák')).toBe(1)
  })
})

describe('similarity', () => {
  it('is 1 for identical strings, case/whitespace-insensitively', () => {
    expect(similarity('Novák', 'novák')).toBe(1)
    expect(similarity('  Novák  ', 'Novák')).toBe(1)
  })

  it('is 0 when either side is empty', () => {
    expect(similarity('', 'Novák')).toBe(0)
    expect(similarity('Novák', '')).toBe(0)
  })

  it('scales with edit distance relative to the longer string', () => {
    expect(similarity('Novak', 'Novák')).toBe(0.8)
  })
})
