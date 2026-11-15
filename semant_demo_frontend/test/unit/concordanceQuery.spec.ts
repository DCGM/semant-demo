import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { QBtn, QChip, QInput, QSelect, Quasar } from 'quasar'

import {
  Cardinality, SpanType, TextScope, ValueKind, type AnnotatedDocument, type AnnotationListRow, type Attribute
} from 'src/generated/api'
import ConcordanceFilterChips from 'src/features/annotations/concordance/ConcordanceFilterChips.vue'
import ConcordanceTable from 'src/features/annotations/concordance/ConcordanceTable.vue'
import ConcordanceToolbar from 'src/features/annotations/concordance/ConcordanceToolbar.vue'
import { defaultFilters, type ConcordanceFilters } from 'src/features/annotations/concordance/concordanceStore'
import { concordanceChips, scopeHintText, titleProblem } from 'src/features/annotations/concordance/filterChips'
import { markMatches, queryWords, splitParts } from 'src/features/annotations/concordance/textMatches'

// The annotation query of the workspace (#663): lexical matches marked where the server matched
// them, every active filter as a removable chip, the text scope and the shared document filters.

const marks = (text: string, words: string[]) => markMatches(text, words).filter(p => p.match).map(p => p.text)

describe('annotation halves (#665)', () => {
  const texts = (parts: { text: string }[]) => parts.map(p => p.text)

  it('splits at the middle, also inside a marked match, keeping every character once', () => {
    const [head, tail] = splitParts(markMatches('Jan Novák z Lhoty', ['novák']))
    expect([texts(head), texts(tail)]).toEqual([['Jan ', 'Novák'], [' z Lhoty']])
    const [h2, t2] = splitParts(markMatches('Pan Novák', ['novák']))
    expect([h2, t2]).toEqual([[{ text: 'Pan ', match: false }, { text: 'N', match: true }], [{ text: 'ovák', match: true }]])
  })

  it('never splits a surrogate pair, and leaves an empty text empty', () => {
    const halves = (text: string) => splitParts([{ text, match: false }]).map(h => texts(h).join(''))
    expect(halves('ab😀')).toEqual(['ab', '😀'])
    expect(halves('a😀b')).toEqual(['a😀', 'b'])
    expect(splitParts([])).toEqual([[], []])
  })
})

describe('lexical matches', () => {
  it('marks a query word inside a word, ignoring case, keeping the text unchanged', () => {
    const parts = markMatches('Pan Novák z Nováků, novák.', ['NOVÁ'])
    expect(parts.map(p => p.text).join('')).toBe('Pan Novák z Nováků, novák.')
    expect(marks('Pan Novák z Nováků, novák.', ['NOVÁ'])).toEqual(['Nová', 'Nová', 'nová'])
  })

  it('does not match across words or punctuation, nor without diacritics', () => {
    expect(marks('Nová-k', ['novák'])).toEqual([])
    expect(marks('škola', ['skola'])).toEqual([])
  })

  it('joins overlapping matches of several words', () => {
    expect(marks('rodinu', ['rod', 'odin'])).toEqual(['rodin'])
  })

  it('splits the query into composed words, as the server does', () => {
    expect(queryWords(' zdeňku,  Brno ')).toEqual(['zdeňku', 'Brno'])
    expect(queryWords('')).toEqual([])
  })

  it('leaves non-BMP and empty text intact', () => {
    expect(markMatches('Karel 😀', ['karel']).map(p => p.text)).toEqual(['Karel', ' 😀'])
    expect(markMatches('', ['x'])).toEqual([])
  })
})

describe('matching rules shown to the user', () => {
  it('describes word containment per scope, never a phrase or substring search', () => {
    expect(scopeHintText(TextScope.annotation)).toMatch(/inside a word of the annotation.*Not a phrase search/)
    expect(scopeHintText(TextScope.context)).toMatch(/left or right context.*different fields/)
    expect(scopeHintText(TextScope.both)).toMatch(/annotation or its context/)
  })

  it('checks a title filter by the server rules before adding it', () => {
    expect(titleProblem('kron*', [])).toMatch(/Wildcards/)
    expect(titleProblem('a b', [])).toMatch(/at least one word/)
    expect(titleProblem('a kronika z Lhoty', [])).toBeNull()
    expect(titleProblem('one two three four five six', [])).toMatch(/At most 5 words/)
    expect(titleProblem('kronika', Array(10).fill('x'))).toMatch(/At most 10 titles/)
  })
})

const attribute: Attribute = {
  id: 'a1',
  name: 'Speaker',
  cardinality: Cardinality.single,
  allTags: true,
  tagIds: [],
  values: [{ id: 'v1', label: 'politician', kind: ValueKind.value }]
} as Attribute
const documents: AnnotatedDocument[] = [
  { id: 'd1', title: 'Kronika', year: 1851, library: 'mzk', language: 'ces', count: 4, available: true },
  { id: 'd2', title: 'Dopisy', year: 1902, library: 'nkp', language: 'ces', count: 2, available: true },
  { id: 'd3', count: 1, available: false }
]
const tags = [{ id: 't1', name: 'Person', shorthand: 'P', color: '#f00', pictogram: '', definition: '', examples: [] }]

function filters (change: Partial<ConcordanceFilters>): ConcordanceFilters {
  return { ...defaultFilters(), ...change }
}

describe('active filter chips', () => {
  it('lists nothing for the default filters', () => {
    expect(concordanceChips(defaultFilters(), tags, documents, [attribute])).toEqual([])
  })

  it('lists every active filter with the change that removes it', () => {
    const f = filters({
      tagIds: ['t1'],
      types: [SpanType.neg],
      text: ' praha ',
      textScope: TextScope.context,
      documentIds: ['d1', 'd3'],
      documentFilters: { yearMin: 1850, yearMax: 1900, titleContains: ['kronika'], libraries: ['mzk'], languages: ['ces'] },
      attributeValues: ['a1:v1'],
      attributeUnassigned: ['a1']
    })
    const chips = concordanceChips(f, tags, documents, [attribute])
    expect(chips.map(c => `${c.group}: ${c.label}`)).toEqual([
      'Tag: Person', 'Status: Rejected', 'Text in context: praha', 'Source: Kronika', 'Source: Unavailable source',
      'Years: 1850–1900', 'Title contains: kronika', 'Library: Moravian Library (mzk)', 'Language: Czech (ces)',
      'Speaker: politician', 'Speaker: not assigned'
    ])
    const remove = (label: string) => chips.find(c => `${c.group}: ${c.label}` === label)!.remove
    expect(remove('Status: Rejected')).toEqual({ types: defaultFilters().types })
    expect(remove('Text in context: praha')).toEqual({ text: '' })
    expect(remove('Source: Kronika')).toEqual({ documentIds: ['d3'] })
    expect(remove('Years: 1850–1900').documentFilters).toMatchObject({ yearMin: undefined, yearMax: undefined, libraries: ['mzk'] })
    expect(remove('Library: Moravian Library (mzk)').documentFilters).toMatchObject({ libraries: [], languages: ['ces'] })
    expect(remove('Speaker: politician')).toEqual({ attributeValues: [] })
  })
})

describe('components', () => {
  const mounted: VueWrapper[] = []
  afterEach(() => {
    mounted.splice(0).forEach(w => w.unmount())
    document.body.innerHTML = ''
  })
  const mountIt = <T>(component: T, props: Record<string, unknown>) => {
    const wrapper = mount(component as never, { props: props as never, global: { plugins: [Quasar] }, attachTo: document.body })
    mounted.push(wrapper)
    return wrapper
  }

  it('removes one filter per chip and resets all', async () => {
    const chips = mountIt(ConcordanceFilterChips, {
      filters: filters({ tagIds: ['t1'], text: 'praha' }), tags, documents, attributes: []
    })
    const all = chips.findAllComponents(QChip)
    expect(all.map(c => c.find('.filter-chips__value').text())).toEqual(['Person', 'praha'])
    expect(all[1].props('removeAriaLabel')).toBe('Remove filter Text in annotation: praha')
    all[0].vm.$emit('remove')
    chips.findComponent(QBtn).vm.$emit('click')
    expect(chips.emitted('change')).toEqual([[{ tagIds: [] }]])
    expect(chips.emitted('reset')).toHaveLength(1)

    await chips.setProps({ filters: defaultFilters() } as never)
    expect(chips.find('[data-testid="concordance-chips"]').exists()).toBe(false)
  })

  it('chooses the text scope and says how its words match', async () => {
    const toolbar = mountIt(ConcordanceToolbar, { filters: defaultFilters(), tags: [], documents })
    const scope = toolbar.findAllComponents(QSelect).find(s => s.props('label') === 'Search in')!
    expect((scope.props('options') as { label: string }[]).map(o => o.label)).toEqual(['Annotation', 'Context', 'Both'])
    scope.vm.$emit('update:modelValue', TextScope.both)
    expect(toolbar.emitted('change')).toEqual([[{ textScope: TextScope.both }]])

    await toolbar.setProps({ filters: filters({ textScope: TextScope.context }) } as never)
    const text = toolbar.findAllComponents(QInput).find(i => i.props('label') === 'Context text')!
    expect(text.props('hint')).toBe(scopeHintText(TextScope.context))
  })

  it('edits the shared document filters, with the annotated documents\' libraries and languages', async () => {
    const toolbar = mountIt(ConcordanceToolbar, {
      filters: filters({ documentFilters: { yearMin: 1800, libraries: ['mzk'] } }), tags: [], documents
    })
    const open = toolbar.findAllComponents(QBtn).find(b => b.attributes('data-testid') === 'concordance-document-filters')!
    expect(open.text()).toContain('Document filters (1)')
    await open.trigger('click')
    await flushPromises()
    const select = (label: string) => toolbar.findAllComponents(QSelect).find(s => s.props('label') === label)!
    expect(select('Source library').props('options')).toEqual([
      { value: 'mzk', label: 'Moravian Library (mzk) (4)' }, { value: 'nkp', label: 'National Library of the Czech Republic (nkp) (2)' }
    ])
    expect(select('Document language').props('options')).toEqual([{ value: 'ces', label: 'Czech (ces) (6)' }])
    select('Document language').vm.$emit('update:modelValue', ['ces'])
    const year = toolbar.findAllComponents(QInput).find(i => i.props('label') === 'To year')!
    year.vm.$emit('update:modelValue', '1900')
    expect(toolbar.emitted('change')).toEqual([
      [{ documentFilters: { yearMin: 1800, libraries: ['mzk'], languages: ['ces'] } }],
      [{ documentFilters: { yearMin: 1800, yearMax: 1900, libraries: ['mzk'] } }]
    ])
  })

  it('marks lexical matches only in the searched fields, apart from the annotation highlight', async () => {
    const row: AnnotationListRow = {
      id: 'r1',
      tagId: 't1',
      type: SpanType.pos,
      chunkId: 'c1',
      documentId: 'd1',
      start: 0,
      end: 5,
      revision: 1,
      textStatus: 'ready',
      text: 'Praha',
      leftContext: 'z Prahy do ',
      rightContext: ' a do Prahy',
      documentAvailable: true,
      documentTitle: 'Kronika',
      documentYear: 1851
    } as AnnotationListRow
    const table = mountIt(ConcordanceTable, { rows: [row], tags, selected: new Set(), query: 'prah', queryScope: TextScope.annotation })
    // A match the annotation's middle cuts is marked in both halves (#665): joined per field here.
    const marked = () => ['left', 'key', 'right'].map(c => {
      const text = table.findAll(`[data-testid="kwic-text"] .kwic__${c} mark.kwic__match`).map(m => m.text()).join('')
      return text ? [text] : []
    })
    expect(marked()).toEqual([[], ['Prah'], []])
    expect(table.get('[data-testid="kwic-text"] .kwic__key-label').text()).toBe('Praha')

    await table.setProps({ queryScope: TextScope.context } as never)
    expect(marked()).toEqual([['Prah'], [], ['Prah']])
    expect(table.find('[data-testid="kwic-row"] .kwic__left').text()).toBe('z Prahy do')
    await table.setProps({ queryScope: TextScope.both, query: '' } as never)
    expect(marked()).toEqual([[], [], []])
  })
})
