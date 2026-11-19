import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import type { Tag } from 'src/generated/api'
import { useTagSearch } from 'src/features/annotations/useTagSearch'

const tag = (id: string, name: string, shorthand = ''): Tag =>
  ({ id, name, shorthand, color: '#000', pictogram: '', definition: '', examples: [] })

describe('useTagSearch', () => {
  const tags = ref([tag('a', 'Rakousko-Uhersko', 'AU'), tag('b', 'Francie', 'FR'), tag('c', 'Osoba')])

  it('keeps all tags for a blank search', () => {
    const { filteredTags } = useTagSearch(tags, ref('  '))
    expect(filteredTags.value.map(t => t.id)).toEqual(['a', 'b', 'c'])
  })

  it('matches the name case-insensitively', () => {
    const { filteredTags } = useTagSearch(tags, ref('franc'))
    expect(filteredTags.value.map(t => t.id)).toEqual(['b'])
  })

  it('matches the shorthand case-insensitively (#770)', () => {
    const { filteredTags } = useTagSearch(tags, ref('au'))
    expect(filteredTags.value.map(t => t.id)).toEqual(['a'])
  })

  it('lists a tag once when both its name and shorthand match', () => {
    const { filteredTags } = useTagSearch(tags, ref('fr'))
    expect(filteredTags.value.map(t => t.id)).toEqual(['b'])
  })
})
