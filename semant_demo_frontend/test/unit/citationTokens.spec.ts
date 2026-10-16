import { describe, expect, it } from 'vitest'
import { tokenizeCitations } from 'src/shared/citationTokens'

describe('tokenizeCitations', () => {
  it('splits text around [docN] markers, resolving each to its citation', () => {
    const tokens = tokenizeCitations('Text [doc2] more [doc1].', (number) => ({ label: `L${number}` }))

    expect(tokens).toEqual([
      { type: 'text', value: 'Text ' },
      { type: 'citation', label: 'L2' },
      { type: 'text', value: ' more ' },
      { type: 'citation', label: 'L1' },
      { type: 'text', value: '.' }
    ])
  })

  it('renders an unresolved citation number as plain text, not a dead link', () => {
    const tokens = tokenizeCitations('See [doc3].', () => null as { type: 'citation' } | null)

    // Adjacent text segments aren't merged (matching the pre-existing behavior this was
    // extracted from) — only their concatenation has to reproduce the original text.
    expect(tokens.every((t) => t.type === 'text')).toBe(true)
    expect(tokens.map((t) => (t.type === 'text' ? t.value : '')).join('')).toBe('See [doc3].')
  })

  it('returns a single text token for text with no citation markers', () => {
    expect(tokenizeCitations('No citations here.', () => ({ label: '?' })))
      .toEqual([{ type: 'text', value: 'No citations here.' }])
  })
})
