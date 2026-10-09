import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { Quasar } from 'quasar'

import { FilterType, type SearchFilter } from 'src/generated/api'
import { classificationRows } from 'src/features/search/classifications'
import ResultClassifications from 'src/features/search/ResultClassifications.vue'

const nominal = (id: string, name: string, values: [string, string][]): SearchFilter => ({
  id,
  name,
  type: FilterType.nominal,
  description: '',
  targetProperty: id,
  values: values.map(([backendForm, userForm]) => ({ backendForm, userForm }))
})

const filters: SearchFilter[] = [
  nominal('communicative_mode', 'Communicative Mode', [['narration', 'Narration']]),
  nominal('style', 'Style', [['formal', 'Formal'], ['informal', 'Informal']]),
  nominal('subject_domain', 'Subject Domain', [['ddc_900_history_geography', 'DDC 900 History Geography']])
]

const metadata = {
  communicative_mode: ['narration'],
  style: ['formal', 'informal'],
  subject_domain: ['ddc_900_history_geography', 'news_and_current_affairs'],
  textual_stance: ['neutral_descriptive'],
  complexity: ['moderate']
}

function mountClassifications (props: Record<string, unknown>) {
  return mount(ResultClassifications, { props: { filters, ...props }, global: { plugins: [[Quasar, {}]] } })
}

const shownLines = (wrapper: ReturnType<typeof mountClassifications>) =>
  wrapper.findAll('.classification-row').map(row => row.text())

describe('classificationRows', () => {
  it('uses filter names and values, falls back for unknown ones, keeps the backend order', () => {
    expect(classificationRows(metadata, filters)).toEqual([
      { key: 'communicative_mode', label: 'Communicative Mode', values: ['Narration'] },
      { key: 'style', label: 'Style', values: ['Formal', 'Informal'] },
      { key: 'subject_domain', label: 'Subject Domain', values: ['DDC 900 History Geography', 'News And Current Affairs'] },
      { key: 'textual_stance', label: 'Textual Stance', values: ['Neutral Descriptive'] },
      { key: 'complexity', label: 'Complexity', values: ['Moderate'] }
    ])
  })

  it('has no rows without metadata, without filters loaded or for empty values', () => {
    expect(classificationRows(undefined, filters)).toEqual([])
    expect(classificationRows({ style: [] }, filters)).toEqual([])
    expect(classificationRows({ style: ['formal'] }, [])).toEqual([{ key: 'style', label: 'Style', values: ['Formal'] }])
  })
})

describe('ResultClassifications', () => {
  it('shows the first three classifications and expands to all of them and back', async () => {
    const wrapper = mountClassifications({ metadata })

    expect(shownLines(wrapper)).toEqual([
      'Communicative Mode: Narration',
      'Style: Formal, Informal',
      'Subject Domain: DDC 900 History Geography, News And Current Affairs'
    ])
    const toggle = wrapper.find('button')
    expect(toggle.text()).toBe('Show more (2)')

    await toggle.trigger('click')
    expect(shownLines(wrapper)).toHaveLength(5)
    expect(shownLines(wrapper)[4]).toBe('Complexity: Moderate')
    expect(toggle.text()).toBe('Show less')

    await toggle.trigger('click')
    expect(shownLines(wrapper)).toHaveLength(3)
  })

  it('expands each result on its own', async () => {
    const first = mountClassifications({ metadata })
    const second = mountClassifications({ metadata })

    await first.find('button').trigger('click')

    expect([shownLines(first).length, shownLines(second).length]).toEqual([5, 3])
  })

  it('has no toggle for a short list and renders nothing without classifications', () => {
    const short = mountClassifications({ metadata: { style: ['formal'] } })
    expect(shownLines(short)).toEqual(['Style: Formal'])
    expect(short.find('button').exists()).toBe(false)

    for (const empty of [undefined, {}]) {
      expect(mountClassifications({ metadata: empty }).find('.result-classifications').exists()).toBe(false)
    }
  })
})
