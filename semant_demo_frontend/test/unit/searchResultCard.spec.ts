import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Quasar } from 'quasar'

import type { TextChunkWithDocument } from 'src/generated/api'
import SearchResultCard from 'src/features/search/SearchResultCard.vue'
import { CONSTRAINED_RESULT_WIDTH, escapeClearsSelection, isConstrainedResultWidth } from 'src/features/search/resultLayout'

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

/** jsdom has no layout: give cards `cardWidth` and passages taller than their box when clipped. */
function layout (cardWidth: number) {
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(function (this: HTMLElement) {
    return this.classList.contains('search-result') ? cardWidth : 0
  })
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockImplementation(function (this: HTMLElement) {
    return this.classList.contains('search-result__text--preview') ? 120 : 800
  })
  vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(800)
}

afterEach(() => {
  vi.restoreAllMocks()
})

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

  it('indents only the title row; metadata, source and passage align with the card', () => {
    const wrapper = mountCard()
    const titleRow = wrapper.get('.search-result__title-row')

    expect(titleRow.find('[role="checkbox"]').exists()).toBe(true)
    for (const selector of ['.search-result__meta', '.search-result__source']) {
      const el = wrapper.get(selector)
      expect(titleRow.element.contains(el.element)).toBe(false)
      expect(el.element.parentElement).toBe(wrapper.get('.search-result__header').element)
    }
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

  it('shows the complete passage, metadata and source in a wide card', async () => {
    layout(CONSTRAINED_RESULT_WIDTH + 200)
    const wrapper = mountCard()
    await flushPromises()
    const text = wrapper.get('.search-result__text')

    expect(text.text()).toBe(longText)
    expect(text.classes()).not.toContain('search-result__text--preview')
    expect(wrapper.find('.search-result__toggle').exists()).toBe(false) // no Show full text control
    const header = wrapper.get('.search-result__header').text()
    for (const value of ['Jan Novák', '1921', 'cs', 'Pages: 3–4', 'Source: Kronika obce Lhota']) {
      expect(header).toContain(value)
    }
  })

  it('previews the passage in a narrow card, expandable to the complete text', async () => {
    layout(CONSTRAINED_RESULT_WIDTH - 200)
    const wrapper = mountCard()
    await flushPromises()
    const text = wrapper.get('.search-result__text')
    const toggle = () => wrapper.get('.search-result__toggle')

    expect(text.classes()).toContain('search-result__text--preview')
    expect(text.text()).toBe(longText) // clipped visually, never cut
    expect(toggle().text()).toBe('Show full text')
    expect(toggle().attributes('aria-expanded')).toBe('false')
    expect(toggle().attributes('aria-controls')).toBe(text.attributes('id'))
    expect(wrapper.get('.search-result__header').text()).toContain('Source: Kronika obce Lhota')

    await toggle().trigger('click')
    expect(text.classes()).not.toContain('search-result__text--preview')
    expect(toggle().text()).toBe('Show less')
    expect(toggle().attributes('aria-expanded')).toBe('true')

    await toggle().trigger('click')
    expect(text.classes()).toContain('search-result__text--preview')
  })

  it('offers no toggle when a narrow card fits the whole passage', async () => {
    layout(CONSTRAINED_RESULT_WIDTH - 200)
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(100)
    const wrapper = mountCard()
    await flushPromises()

    expect(wrapper.find('.search-result__toggle').exists()).toBe(false)
  })
})

describe('isConstrainedResultWidth', () => {
  it('treats unmeasured (0) and wide cards as wide', () => {
    expect(isConstrainedResultWidth(0)).toBe(false)
    expect(isConstrainedResultWidth(CONSTRAINED_RESULT_WIDTH)).toBe(false)
    expect(isConstrainedResultWidth(CONSTRAINED_RESULT_WIDTH - 1)).toBe(true)
  })
})

describe('escapeClearsSelection', () => {
  function press (target: Element, init: Partial<Pick<KeyboardEvent, 'key' | 'shiftKey'>> = {}) {
    let result: boolean | undefined
    const listener = (event: Event) => { result = escapeClearsSelection(event as KeyboardEvent) }
    window.addEventListener('keydown', listener)
    target.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true, ...init }))
    window.removeEventListener('keydown', listener)
    return result
  }

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('clears from the page or a focused result control', () => {
    document.body.innerHTML = '<div role="checkbox" tabindex="0"></div>'
    expect(press(document.body)).toBe(true)
    expect(press(document.querySelector('[role="checkbox"]') as Element)).toBe(true)
  })

  it('leaves Escape to fields, menus, dialogs and overlay drawers', () => {
    document.body.innerHTML = '<input id="q"><div role="combobox"><span id="c"></span></div>'
    expect(press(document.getElementById('q') as Element)).toBe(false)
    expect(press(document.getElementById('c') as Element)).toBe(false)

    for (const overlay of ['<div class="q-menu"></div>', '<div class="q-dialog"></div>', '<div class="q-drawer__backdrop"></div>']) {
      document.body.innerHTML = overlay
      expect(press(document.body)).toBe(false)
    }
    document.body.innerHTML = '<div class="q-drawer__backdrop hidden"></div>' // closed drawer
    expect(press(document.body)).toBe(true)
  })

  it('ignores other keys, modified and already handled Escapes', () => {
    expect(press(document.body, { key: 'Enter' })).toBe(false)
    expect(press(document.body, { shiftKey: true })).toBe(false)
    const handled = (event: Event) => event.preventDefault()
    document.body.addEventListener('keydown', handled)
    expect(press(document.body)).toBe(false)
    document.body.removeEventListener('keydown', handled)
  })
})
