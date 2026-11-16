import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { Quasar } from 'quasar'
import {
  AnnotationSort, RetrievalMode, SpanType, TextScope, TextStatus, type AnnotationListRow, type Tag
} from 'src/generated/api'
import ConcordanceTable from 'src/features/annotations/concordance/ConcordanceTable.vue'
import ConcordanceToolbar from 'src/features/annotations/concordance/ConcordanceToolbar.vue'
import { defaultFilters, type ConcordanceFilters } from 'src/features/annotations/concordance/concordanceStore'

// #665: continuous KWIC rows under three text headers, header sorts and header filter buttons.

const tag: Tag = { id: 't', name: 'Osoba', color: '#1976d2' } as Tag

function annotation (id: string, overrides: Partial<AnnotationListRow> = {}): AnnotationListRow {
  return {
    id,
    tagId: 't',
    type: SpanType.pos,
    text: 'Jan Novák',
    leftContext: 'přijel do Lhoty hejtman ',
    rightContext: ' a ubytoval se\nv hostinci',
    textStatus: TextStatus.ready,
    documentId: 'd',
    documentTitle: 'Kronika obce Lhota',
    documentYear: 1851,
    documentAvailable: true,
    ...overrides
  } as AnnotationListRow
}

function mountTable (filters: Partial<ConcordanceFilters> = {}, rows = [annotation('a')]) {
  return mount(ConcordanceTable, {
    props: { rows, tags: [tag], selected: new Set<string>(), filters: { ...defaultFilters(), ...filters } },
    global: { plugins: [[Quasar, {}]] }
  })
}

const head = (wrapper: ReturnType<typeof mountTable>, id: string) => wrapper.get(`[data-testid="kwic-head-${id}"]`)

describe('concordance table', () => {
  it('renders the context, annotation and context as one cell under the three text headers', () => {
    const wrapper = mountTable()
    const cells = wrapper.findAll('[data-testid="kwic-row"] [role="gridcell"]')
    const text = wrapper.get('[data-testid="kwic-text"]')
    expect(text.attributes('aria-colspan')).toBe('3')
    expect(cells.filter(c => c.attributes('aria-colspan') === '3')).toHaveLength(1)
    // The space before the annotation survives the line end of the left context; line breaks
    // show as spaces; the right context follows the annotation in the same flow.
    expect(text.get('.kwic__left').element.textContent).toBe('přijel do Lhoty hejtman\u00a0')
    expect(text.get('.kwic__key-label').text()).toBe('Jan Novák')
    // Read as one text; the visible halves are hidden from assistive technology.
    expect(text.findAll('.kwic__key-head, .kwic__key-tail').map(h => h.attributes('aria-hidden'))).toEqual(['true', 'true'])
    expect(text.get('.kwic__right').element.textContent).toBe(' a ubytoval se v hostinci')
    expect(text.findAll(':scope > span').map(s => s.classes()[0])).toEqual(['kwic__left', 'kwic__key', 'kwic__right'])
    const name = (h: ReturnType<typeof wrapper.get>) => h.find('.kwic-head__label').exists() ? h.get('.kwic-head__label').text() : h.text()
    expect(wrapper.findAll('[role="columnheader"]').map(name))
      .toEqual(['', 'Left context', 'Annotation', 'Right context', 'Tag · status', 'Source', 'Year'])
  })

  it('keeps the spaces an annotation starts or ends with, and shows its line breaks as spaces', () => {
    const wrapper = mountTable({}, [annotation('a', { leftContext: 'den', text: ' gegenseitigen\nBeistand ', rightContext: 'ablehnen' })])
    expect(wrapper.get('[data-testid="kwic-text"] .kwic__key-label').element.textContent).toBe(' gegenseitigen Beistand ')
  })

  it('shows the annotation in two halves, the start of the first and the end of the second', () => {
    const wrapper = mountTable({}, [annotation('a', { text: 'přijel do Lhoty hejtman' })])
    expect([wrapper.get('.kwic__key-head').text(), wrapper.get('.kwic__key-tail').text()]).toEqual(['přijel do Lh', 'oty hejtman'])
  })

  it('marks the active sort and its direction, and leaves the context headers unsortable', () => {
    const wrapper = mountTable({ sort: AnnotationSort.year, descending: true })
    expect(head(wrapper, 'year').attributes('aria-sort')).toBe('descending')
    expect(head(wrapper, 'source').attributes('aria-sort')).toBe('none')
    expect(head(wrapper, 'annotation').attributes('aria-sort')).toBe('none')
    for (const id of ['left', 'right']) {
      expect(head(wrapper, id).attributes('aria-sort')).toBeUndefined()
      expect(head(wrapper, id).find('button[data-testid^="kwic-sort"]').exists()).toBe(false)
      expect(head(wrapper, id).text()).toContain(id === 'left' ? 'Left context' : 'Right context')
    }
    expect(wrapper.get('[data-testid="kwic-sort-year"]').attributes('aria-label')).toBe('Year, sorted descending; sort ascending')
  })

  it('sorts a new column ascending and toggles the direction of the active one', async () => {
    const wrapper = mountTable({ sort: AnnotationSort.document, descending: false })
    await wrapper.get('[data-testid="kwic-sort-annotation"]').trigger('click')
    await wrapper.get('[data-testid="kwic-sort-source"]').trigger('click')
    expect(wrapper.emitted('sort')).toEqual([[AnnotationSort.text, false], [AnnotationSort.document, true]])

    await wrapper.setProps({ filters: { ...defaultFilters(), sort: AnnotationSort.document, descending: true } })
    await wrapper.get('[data-testid="kwic-sort-source"]').trigger('click')
    expect(wrapper.emitted('sort')?.[2]).toEqual([AnnotationSort.document, false])
  })

  it('offers no header sort for ranked results', async () => {
    const wrapper = mountTable({ mode: RetrievalMode.semantic, text: 'hejtman' })
    for (const id of ['annotation', 'source', 'year']) {
      expect(head(wrapper, id).attributes('aria-sort')).toBe('none')
      expect(wrapper.get(`[data-testid="kwic-sort-${id}"]`).attributes('disabled')).toBeDefined()
    }
    await wrapper.get('[data-testid="kwic-sort-year"]').trigger('click')
    expect(wrapper.emitted('sort')).toBeUndefined()
    // The words are a filter whatever ranks: the text headers still add words.
    expect(wrapper.get('[data-testid="kwic-filter-annotation"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[data-testid="kwic-filter-source"]').attributes('disabled')).toBeUndefined()
  })

  it('brings up each column\'s filter without opening, checking or focusing a row', async () => {
    const wrapper = mountTable()
    for (const id of ['left', 'annotation', 'right', 'source', 'year']) {
      await wrapper.get(`[data-testid="kwic-filter-${id}"]`).trigger('click')
    }
    expect(wrapper.emitted('filter')).toEqual([['context'], ['annotation'], ['context'], ['source'], ['year']])
    expect(wrapper.emitted('open')).toBeUndefined()
    expect(wrapper.emitted('toggle')).toBeUndefined()
  })

  it('shows which header filters are active, in the field the text scope searches', () => {
    const label = (wrapper: ReturnType<typeof mountTable>, id: string) =>
      wrapper.get(`[data-testid="kwic-filter-${id}"]`).attributes('aria-label')
    const plain = mountTable()
    expect(label(plain, 'annotation')).toBe('Filter by words in the annotation')
    expect(label(plain, 'left')).toBe('Filter by words in the context')

    const context = mountTable({
      text: 'hejtman', textScope: TextScope.context, documentIds: ['d'], documentFilters: { yearMin: 1800 }
    })
    expect(label(context, 'annotation')).toBe('Filter by words in the annotation')
    expect(label(context, 'left')).toBe('Filter by words in the context (active)')
    expect(label(context, 'right')).toBe('Filter by words in the context (active)')
    expect(label(context, 'source')).toBe('Filter by source (active)')
    expect(label(context, 'year')).toBe('Filter by publication year (active)')

    const both = mountTable({ text: 'hejtman', textScope: TextScope.both })
    expect(label(both, 'annotation')).toBe('Filter by words in the annotation (active)')
    expect(label(both, 'left')).toBe('Filter by words in the context (active)')
  })
})

describe('concordance table open row (#704)', () => {
  const original = { scroll: HTMLElement.prototype.scrollIntoView, matchMedia: window.matchMedia }
  afterEach(() => {
    HTMLElement.prototype.scrollIntoView = original.scroll
    window.matchMedia = original.matchMedia
  })

  function mountRows (attachTo?: HTMLElement) {
    const scrolled: Array<{ id: string | null, options: ScrollIntoViewOptions }> = []
    HTMLElement.prototype.scrollIntoView = function (this: HTMLElement, options?: boolean | ScrollIntoViewOptions) {
      scrolled.push({ id: this.closest('[data-testid="kwic-row"]') ? this.textContent : null, options: options as ScrollIntoViewOptions })
    }
    const wrapper = mount(ConcordanceTable, {
      props: {
        rows: [annotation('a'), annotation('b', { text: 'Lhoty' }), annotation('c', { text: 'Brně' })],
        tags: [tag],
        selected: new Set<string>(),
        filters: defaultFilters(),
        focusedId: 'a'
      },
      global: { plugins: [[Quasar, {}]] },
      attachTo
    })
    return { wrapper, scrolled }
  }

  it('scrolls a newly open row into view minimally and vertically, without moving focus', async () => {
    const outside = document.createElement('button')
    document.body.appendChild(outside)
    outside.focus()
    const host = document.body.appendChild(document.createElement('div'))
    const { wrapper, scrolled } = mountRows(host)
    await wrapper.setProps({ focusedId: 'c' })
    await wrapper.vm.$nextTick()
    expect(scrolled).toHaveLength(1)
    expect(scrolled[0].id).toContain('Brně')
    expect(scrolled[0].options).toEqual({ block: 'nearest', inline: 'nearest', behavior: 'smooth' })
    expect(document.activeElement).toBe(outside)
    // The row stays the grid's tab stop for a return by keyboard.
    expect(wrapper.findAll('[data-testid="kwic-row"]')[2].attributes('tabindex')).toBe('0')
    wrapper.unmount()
    host.remove()
    outside.remove()
  })

  it('keeps the row clear of the fixed app header and of a sticky header stuck at the top', async () => {
    const cover = (className: string, position: string, top: number, bottom: number) => {
      const el = document.body.appendChild(document.createElement('div'))
      el.className = className
      el.style.position = position
      el.getBoundingClientRect = () => ({ top, bottom, height: bottom - top } as DOMRect)
      return el
    }
    const covers = [
      cover('q-header', 'fixed', 0, 64),
      cover('', 'sticky', 0, 100), // not marked as a cover
      cover('later', 'sticky', 300, 340) // marked, but not stuck at the top
    ]
    covers[2].setAttribute('data-covers-top', '')
    const { wrapper } = mountRows()
    await wrapper.setProps({ focusedId: 'b' })
    await wrapper.vm.$nextTick()
    const rowEl = () => wrapper.findAll('[data-testid="kwic-row"]')[1].element as HTMLElement
    expect(rowEl().style.scrollMarginTop).toBe('72px')
    // A sticky header stuck below the app header (e.g. a toolbar) is covered too.
    covers[2].getBoundingClientRect = () => ({ top: 64, bottom: 112, height: 48 } as DOMRect)
    await wrapper.setProps({ focusedId: 'a' })
    await wrapper.setProps({ focusedId: 'b' })
    await wrapper.vm.$nextTick()
    expect(rowEl().style.scrollMarginTop).toBe('120px')
    covers.forEach(el => el.remove())
  })

  it('does not animate with reduced motion, and ignores rows of another page', async () => {
    window.matchMedia = ((query: string) => ({ matches: query.includes('reduce') })) as unknown as typeof window.matchMedia
    const { wrapper, scrolled } = mountRows()
    await wrapper.setProps({ focusedId: 'b' })
    await wrapper.vm.$nextTick()
    expect(scrolled.map(s => s.options.behavior)).toEqual(['auto'])
    await wrapper.setProps({ focusedId: 'elsewhere' })
    await wrapper.setProps({ focusedId: null })
    await wrapper.vm.$nextTick()
    expect(scrolled).toHaveLength(1)
  })
})

describe('concordance toolbar header filters', () => {
  function mountToolbar (filters: Partial<ConcordanceFilters>) {
    return mount(ConcordanceToolbar, {
      props: { filters: { ...defaultFilters(), ...filters }, tags: [tag], documents: [] },
      global: { plugins: [[Quasar, {}]] }
    })
  }

  it('selects exactly the header\'s field, also from Both, and keeps a scope that already is it', () => {
    for (const [field, scope] of [['annotation', TextScope.annotation], ['context', TextScope.context]] as const) {
      const fromBoth = mountToolbar({ textScope: TextScope.both, text: 'hejtman' })
      fromBoth.vm.openFilter(field)
      expect(fromBoth.emitted('change')).toEqual([[{ textScope: scope }]])
      const same = mountToolbar({ textScope: scope })
      same.vm.openFilter(field)
      expect(same.emitted('change')).toBeUndefined()
    }
  })

  it('changes no scope for the source and year filters', () => {
    const toolbar = mountToolbar({ textScope: TextScope.both })
    toolbar.vm.openFilter('source')
    toolbar.vm.openFilter('year')
    expect(toolbar.emitted('change')).toBeUndefined()
  })
})

describe('concordance row value filters', () => {
  const menuItem = (testid: string) => document.body.querySelector<HTMLElement>(`[data-testid="${testid}"]`)
  async function until (found: () => unknown) {
    for (let i = 0; i < 50 && !found(); i++) await new Promise(resolve => setTimeout(resolve, 10))
    expect(found()).toBeTruthy()
  }

  it('opens the row menu from the keyboard and refines the query without opening or checking the row', async () => {
    const wrapper = mount(ConcordanceTable, {
      props: { rows: [annotation('a')], tags: [tag], selected: new Set<string>(), filters: defaultFilters() },
      global: { plugins: [[Quasar, {}]] },
      attachTo: document.body
    })
    const row = wrapper.get('[data-testid="kwic-row"]')
    await row.trigger('keydown', { key: 'F10', shiftKey: true })
    await until(() => menuItem('kwic-refine-source-only'))
    expect(menuItem('kwic-refine-group-source')?.textContent).toContain('Source · Kronika obce Lhota')
    // The row whose menu is open is marked.
    expect(row.classes()).toContain('kwic__row--menu')
    // No selected words: no word filter.
    expect(menuItem('kwic-refine-words')).toBeNull()
    // A click on the row while its menu is shown (lifting the finger after a long press) opens nothing.
    await row.trigger('click')
    expect(wrapper.emitted('open')).toBeUndefined()
    menuItem('kwic-refine-year-only')?.click()
    expect(wrapper.emitted('refine')).toEqual([[{ documentFilters: { yearMin: 1851, yearMax: 1851 } }]])
    await wrapper.vm.$nextTick()
    expect(row.classes()).not.toContain('kwic__row--menu')
    expect(wrapper.emitted('open')).toBeUndefined()
    expect(wrapper.emitted('toggle')).toBeUndefined()
    wrapper.unmount()
  })

  it('opens rows again after the row whose menu was open left the page', async () => {
    const wrapper = mount(ConcordanceTable, {
      props: { rows: [annotation('a'), annotation('b')], tags: [tag], selected: new Set<string>(), filters: defaultFilters() },
      global: { plugins: [[Quasar, {}]] },
      attachTo: document.body
    })
    await wrapper.findAll('[data-testid="kwic-row"]')[0].trigger('keydown', { key: 'ContextMenu' })
    await until(() => menuItem('kwic-refine-source-only'))
    // The filter took the row out: its menu goes without closing.
    await wrapper.setProps({ rows: [annotation('b')] })
    await new Promise(resolve => setTimeout(resolve, 450))
    await wrapper.get('[data-testid="kwic-row"]').trigger('click')
    expect(wrapper.emitted('open')).toHaveLength(1)
    wrapper.unmount()
  })

  it('offers the words selected in the row\'s text, and a click that ends a selection does not open the row', async () => {
    const wrapper = mount(ConcordanceTable, {
      props: { rows: [annotation('a')], tags: [tag], selected: new Set<string>(), filters: defaultFilters() },
      global: { plugins: [[Quasar, {}]] },
      attachTo: document.body
    })
    const cell = wrapper.get('.kwic__text .kwic__right').element
    const right = Array.from(cell.childNodes).find(n => n.textContent?.includes('ubytoval')) as Text
    const range = document.createRange()
    range.setStart(right, 3) // " a |ubytoval| se"
    range.setEnd(right, 11)
    window.getSelection()?.removeAllRanges()
    window.getSelection()?.addRange(range)
    const row = wrapper.get('[data-testid="kwic-row"]')
    await row.trigger('click')
    expect(wrapper.emitted('open')).toBeUndefined()

    await row.trigger('keydown', { key: 'ContextMenu' })
    await until(() => menuItem('kwic-refine-words'))
    expect(menuItem('kwic-refine-words')?.textContent).toContain('Filter annotations with “ubytoval” in their context')
    menuItem('kwic-refine-words')?.click()
    expect(wrapper.emitted('refine')).toEqual([[{ text: 'ubytoval', textScope: TextScope.context }]])

    // Right after the menu closed, a click still belongs to its long press; later ones open the row.
    window.getSelection()?.removeAllRanges()
    await row.trigger('click')
    expect(wrapper.emitted('open')).toBeUndefined()
    await new Promise(resolve => setTimeout(resolve, 450))
    await row.trigger('click')
    expect(wrapper.emitted('open')).toHaveLength(1)
    wrapper.unmount()
  })
})
