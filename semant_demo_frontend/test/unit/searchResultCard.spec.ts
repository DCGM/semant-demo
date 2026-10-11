import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { Quasar } from 'quasar'

import type { TextChunkWithDocument } from 'src/generated/api'
import SearchResultCard from 'src/features/search/SearchResultCard.vue'

const longText = Array.from({ length: 40 }, (_, i) => `Sentence ${i + 1} of a long source passage.`).join('\n')

const chunk = {
  id: 'chunk-1',
  title: 'Chunk title',
  queryTitle: null,
  text: longText,
  language: 'cs',
  fromPage: 3,
  toPage: 4,
  documentObject: {
    id: 'doc-1',
    title: 'Kronika obce Lhota',
    author: ['Jan Novák'],
    yearIssued: 1921
  }
} as unknown as TextChunkWithDocument

function mountCard (props: Record<string, unknown> = {}) {
  return mount(SearchResultCard, {
    props: { chunk, number: 12, filters: [], ...props },
    global: { plugins: [[Quasar, {}]] }
  })
}

describe('SearchResultCard', () => {
  it('puts a named checkbox before the title', () => {
    const wrapper = mountCard()
    const checkbox = wrapper.get('[role="checkbox"]')
    const header = wrapper.get('.search-result__header').element

    expect(checkbox.attributes('aria-label')).toBe('Select result 12: Chunk title')
    expect(checkbox.attributes('tabindex')).toBe('0')
    const title = wrapper.get('.search-result__title').element
    // Checkbox precedes the title in document order (left in the no-wrap row).
    expect(checkbox.element.compareDocumentPosition(title) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(header.contains(checkbox.element)).toBe(true)
    expect(wrapper.get('.search-result__title').text()).toBe('12. Chunk title')
  })

  it('reflects and emits the selection', async () => {
    const wrapper = mountCard()
    expect(wrapper.get('[role="checkbox"]').attributes('aria-checked')).toBe('false')
    expect(wrapper.classes()).not.toContain('search-result--selected')

    await wrapper.get('[role="checkbox"]').trigger('click')
    expect(wrapper.emitted('update:selected')).toEqual([[true]])

    await wrapper.setProps({ selected: true })
    expect(wrapper.get('[role="checkbox"]').attributes('aria-checked')).toBe('true')
    expect(wrapper.classes()).toContain('search-result--selected')

    await wrapper.get('[role="checkbox"]').trigger('click')
    expect(wrapper.emitted('update:selected')?.[1]).toEqual([false])
  })

  it('keeps the selected and citation styles distinct', () => {
    const wrapper = mountCard({ selected: true, highlighted: true })
    expect(wrapper.classes()).toEqual(expect.arrayContaining(['search-result--selected', 'citation-target-highlight']))
  })

  it('shows the complete passage, metadata and source', () => {
    const wrapper = mountCard()
    const text = wrapper.get('.search-result__text')

    expect(text.text()).toBe(longText)
    expect(text.attributes('style')).toBeUndefined()
    expect(wrapper.find('button').exists()).toBe(false) // no Show more / collapse control
    const header = wrapper.get('.search-result__header').text()
    for (const value of ['Jan Novák', '1921', 'cs', 'Pages: 3–4', 'Source: Kronika obce Lhota']) {
      expect(header).toContain(value)
    }
  })
})
