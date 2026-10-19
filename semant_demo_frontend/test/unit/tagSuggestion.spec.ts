import { describe, expect, it } from 'vitest'
import type { Tag } from 'src/generated/api'
import { buildTagSuggestions, suggestTagIds } from 'src/features/annotations/tagSuggestion'

const tag = (id: string, name: string, shorthand = ''): Tag =>
  ({ id, name, shorthand, color: '#000', pictogram: '', definition: '', examples: [] })

describe('suggestTagIds', () => {
  it('returns nothing for an empty selection or an empty tag list', () => {
    expect(suggestTagIds('', [tag('1', 'Jan Novák')])).toEqual([])
    expect(suggestTagIds('   ', [tag('1', 'Jan Novák')])).toEqual([])
    expect(suggestTagIds('Jan Novák', [])).toEqual([])
  })

  it('ranks an exact (case-insensitive) match for the whole selection first', () => {
    const tags = [tag('a', 'Karel Čapek'), tag('b', 'Jan Novák'), tag('c', 'Božena Němcová')]
    expect(suggestTagIds('jan novák', tags)).toEqual(['b'])
  })

  it('matches a tag name against a single word of a longer (but <= 5-word) selection', () => {
    const tags = [tag('a', 'Novák'), tag('b', 'Dvořák')]
    expect(suggestTagIds('dopis adresovaný panu Novákovi z', tags)).toContain('a')
  })

  it('matches against the shorthand when the full name does not resemble the selection', () => {
    const tags = [tag('a', 'Rakousko-Uhersko', 'AU'), tag('b', 'Francie', 'FR')]
    expect(suggestTagIds('AU', tags)).toEqual(['a'])
  })

  it('ignores unrelated tags and respects the limit', () => {
    const tags = [tag('a', 'Novák'), tag('b', 'Novotný'), tag('c', 'Dvořák'), tag('d', 'Something else entirely')]
    const result = suggestTagIds('Novák', tags, 2)
    expect(result.length).toBeLessThanOrEqual(2)
    expect(result).not.toContain('d')
  })

  it('skips the similarity check once the selection is longer than 5 words', () => {
    const tags = [tag('a', 'Novák')]
    // Exactly 6 words; the selection would otherwise match "Novák" via its 3rd word.
    expect(suggestTagIds('dopis adresovaný panu Novákovi z Prahy', tags)).toEqual([])
    // 5 words still works.
    expect(suggestTagIds('dopis adresovaný panu Novákovi z', tags)).toEqual(['a'])
  })
})

describe('buildTagSuggestions', () => {
  const tags = [tag('a', 'Novák'), tag('b', 'Zebra'), tag('c', 'Unrelated')]

  it('puts the last-used tag first even when it does not match the selection text', () => {
    expect(buildTagSuggestions('Unrelated', tags, 'a')).toEqual(['a', 'c'])
  })

  it('still suggests the last-used tag for a long (prose) selection with no similarity matches', () => {
    expect(buildTagSuggestions('a long highlighted passage of several sentences', tags, 'a')).toEqual(['a'])
  })

  it('does not duplicate the last-used tag when it is also the best similarity match', () => {
    expect(buildTagSuggestions('Novák', tags, 'a')).toEqual(['a'])
  })

  it('ignores a last-used tag id that no longer exists in this collection', () => {
    expect(buildTagSuggestions('Novák', tags, 'deleted-tag-id')).toEqual(['a'])
  })

  it('falls back to similarity alone when there is no last-used tag', () => {
    expect(buildTagSuggestions('Novák', tags, null)).toEqual(['a'])
  })
})
