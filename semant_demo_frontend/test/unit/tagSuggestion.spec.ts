import { describe, expect, it } from 'vitest'
import type { Tag } from 'src/generated/api'
import { suggestTagIds } from 'src/features/annotations/tagSuggestion'

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

  it('matches a tag name against a single word of a longer selection', () => {
    const tags = [tag('a', 'Novák'), tag('b', 'Dvořák')]
    expect(suggestTagIds('dopis adresovaný panu Novákovi z Prahy', tags)).toContain('a')
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
})
