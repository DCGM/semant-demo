import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Quasar } from 'quasar'

import { FilterType, type SearchFilter } from 'src/generated/api'
import { CATEGORY_COLORS, categoryColor, classificationBadges } from 'src/features/search/classifications'
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
  textual_stance: ['neutral_descriptive']
}

/** jsdom has no layout: badges from the `perLine`-th on report a lower line. */
function layoutLines (perLine: number) {
  vi.spyOn(HTMLElement.prototype, 'offsetTop', 'get').mockImplementation(function (this: HTMLElement) {
    if (!this.classList.contains('classification-badge')) return 0
    const index = Array.from(this.parentElement?.children ?? []).indexOf(this)
    return Math.floor(index / perLine) * 24
  })
}

function mountClassifications (props: Record<string, unknown>) {
  return mount(ResultClassifications, { props: { filters, ...props }, global: { plugins: [[Quasar, {}]] } })
}

const badgeTexts = (wrapper: ReturnType<typeof mountClassifications>) =>
  wrapper.findAll('.classification-badge').map(b => b.text())

afterEach(() => {
  vi.restoreAllMocks()
})

describe('classificationBadges', () => {
  it('gives one badge per value, named by the filters, colored by category, in backend order', () => {
    const badges = classificationBadges(metadata, filters)

    expect(badges.map(b => [b.category, b.value])).toEqual([
      ['Communicative Mode', 'Narration'],
      ['Style', 'Formal'],
      ['Style', 'Informal'],
      ['Subject Domain', 'DDC 900 History Geography'],
      ['Subject Domain', 'News And Current Affairs'], // value no filter defines
      ['Textual Stance', 'Neutral Descriptive'] // category no filter defines
    ])
    expect(badges.map(b => b.color)).toEqual([
      CATEGORY_COLORS[0], CATEGORY_COLORS[1], CATEGORY_COLORS[1], CATEGORY_COLORS[2], CATEGORY_COLORS[2],
      categoryColor('textual_stance', filters)
    ])
  })

  it('gives every configured category its own color', () => {
    const many = Array.from({ length: 18 }, (_, i) => nominal(`category_${i}`, `C${i}`, []))
    expect(new Set(many.map(f => categoryColor(f.targetProperty, many).bg)).size).toBe(18)
  })

  it('has no badges without metadata or values', () => {
    expect(classificationBadges(undefined, filters)).toEqual([])
    expect(classificationBadges({ style: [] }, filters)).toEqual([])
  })
})

describe('ResultClassifications', () => {
  it('shows value badges with the category for tooltips and screen readers', () => {
    layoutLines(10)
    const wrapper = mountClassifications({ metadata })

    expect(badgeTexts(wrapper)[0]).toBe('Communicative Mode: Narration')
    expect(wrapper.findAll('.classification-badge')[1].classes()).toEqual(
      expect.arrayContaining([`bg-${CATEGORY_COLORS[1].bg}`, `text-${CATEGORY_COLORS[1].text}`]))
    expect(wrapper.find('.visually-hidden').text()).toBe('Communicative Mode:')
  })

  it('has no toggle when the badges fit on one line', async () => {
    layoutLines(10)
    const wrapper = mountClassifications({ metadata })
    await flushPromises()

    expect(badgeTexts(wrapper)).toHaveLength(6)
    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.find('.classification-line').classes()).toContain('collapsed')
  })

  it('offers the badges below the first line and expands and collapses them', async () => {
    layoutLines(4)
    const wrapper = mountClassifications({ metadata })
    await flushPromises()
    const toggle = wrapper.find('button')
    const line = wrapper.find('.classification-line')

    expect(toggle.text()).toBe('+2 more')
    await toggle.trigger('click')
    expect([line.classes('collapsed'), toggle.text()]).toEqual([false, 'Show less'])
    await toggle.trigger('click')
    expect([line.classes('collapsed'), toggle.text()]).toEqual([true, '+2 more'])
  })

  it('expands each result on its own', async () => {
    layoutLines(4)
    const first = mountClassifications({ metadata })
    const second = mountClassifications({ metadata })
    await flushPromises()

    await first.find('button').trigger('click')

    expect([first.find('.classification-line').classes('collapsed'),
      second.find('.classification-line').classes('collapsed')]).toEqual([false, true])
  })

  it('renders nothing without classifications', () => {
    for (const empty of [undefined, {}]) {
      expect(mountClassifications({ metadata: empty }).find('.result-classifications').exists()).toBe(false)
    }
  })
})
