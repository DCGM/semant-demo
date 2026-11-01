import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { h } from 'vue'

import ChunkAnnotator from 'src/features/annotations/ChunkAnnotator.vue'
import type { ProjectedSpan } from 'src/features/annotations/useAnnotations'
import DocumentTextPane from 'src/features/documents/viewer/DocumentTextPane.vue'
import type { DocumentTextPaneApi, TextChunk, TextPaneAnnotation } from 'src/features/documents/viewer/documentTextPane'
import type { Tag } from 'src/generated/api'

// Orders 0 and 1 are consecutive; 3 follows a gap. Stored text keeps double spaces, line
// breaks and a character outside the BMP (two UTF-16 code units).
const chunk = (id: string, order: number, text: string, endParagraph = false): TextChunk =>
  ({ id, order, text, endParagraph })
const a = chunk('a', 0, 'First  line\nsecond ')
const b = chunk('b', 1, 'x😀y end', true)
const d = chunk('d', 3, 'After the gap')
const CHUNKS = [a, b, d]

const tag: Tag = { id: 't', name: 'Person', shorthand: '', color: '#ff0000', pictogram: '', definition: '', examples: [] }

function mountPane (props: Record<string, unknown> = {}, slots: Record<string, unknown> = {}) {
  return mount(DocumentTextPane, {
    props: { chunks: CHUNKS, ...props },
    slots: slots as never,
    attachTo: document.body
  })
}

const chunkEl = (id: string) => document.querySelector<HTMLElement>(`[data-chunk-id="${id}"]`)!
// A segment's text node sits between the placeholders of its (absent) selection handles.
const textNodeOf = (id: string) =>
  Array.from(chunkEl(id).querySelector('.text-segment')!.childNodes).find((n) => n.nodeType === Node.TEXT_NODE)!

/** Selects text in the DOM as a user's drag would, then releases the button over the pane. */
async function selectAndRelease (wrapper: ReturnType<typeof mountPane>, start: [Node, number], end: [Node, number]) {
  const range = document.createRange()
  range.setStart(...start)
  range.setEnd(...end)
  const selection = window.getSelection()!
  selection.removeAllRanges()
  selection.addRange(range)
  await wrapper.trigger('mouseup')
}

const originalFetch = globalThis.fetch
let fetchSpy: ReturnType<typeof vi.fn>
beforeEach(() => {
  fetchSpy = vi.fn(() => Promise.reject(new Error('the text pane must not make requests')))
  globalThis.fetch = fetchSpy as unknown as typeof fetch
})

afterEach(() => {
  window.getSelection()?.removeAllRanges()
  globalThis.fetch = originalFetch
  document.body.innerHTML = ''
})

describe('DocumentTextPane, read-only', () => {
  it('renders the stored text unchanged, in paragraphs, without a store or a request', () => {
    // No Pinia, no Quasar, no router: a store or a collection request would fail here.
    const wrapper = mountPane()
    expect(chunkEl('a').textContent).toBe(a.text)
    expect(chunkEl('b').textContent).toBe(b.text)
    expect(wrapper.findAll('p').map((p) => p.findAll('[data-chunk-id]').map((c) => c.attributes('data-chunk-id'))))
      .toEqual([['a', 'b'], ['d']])
    expect(wrapper.classes()).toContain('document-text--preserve-whitespace')
    expect(wrapper.find('.selection-handle').exists()).toBe(false)
    expect(wrapper.find('.is-tagged').exists()).toBe(false)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('reports a selection across chunks in UTF-16 chunk offsets and leaves it to be copied', async () => {
    const wrapper = mountPane()
    // From "line" in chunk a to just after the emoji in chunk b ("x" + 2 code units).
    await selectAndRelease(wrapper, [textNodeOf('a'), 7], [textNodeOf('b'), 3])
    const [[selection]] = wrapper.emitted('select')!
    expect(selection).toEqual({ start: { chunkId: 'a', charOffset: 7 }, end: { chunkId: 'b', charOffset: 3 } })
    expect(window.getSelection()!.toString()).toBe('line\nsecond x😀')
    expect(wrapper.emitted('textClick')).toBeUndefined()
  })

  it('reports a click as a text position, and ignores a selection outside the pane', async () => {
    const outside = document.createElement('div')
    outside.innerHTML = '<div data-chunk-id="z"><span class="text-segment" data-start="0" data-end="5">other</span></div>'
    const wrapper = mountPane()
    // Before the pane, so a selection from it into the pane runs forwards.
    document.body.prepend(outside)

    const selection = window.getSelection()!
    selection.removeAllRanges()
    selection.collapse(textNodeOf('d'), 4)
    await wrapper.trigger('mouseup')
    expect(wrapper.emitted('textClick')![0][0]).toEqual({ chunkId: 'd', charOffset: 4 })

    await selectAndRelease(wrapper, [outside.querySelector('.text-segment')!.firstChild!, 0], [textNodeOf('a'), 3])
    expect(window.getSelection()!.isCollapsed).toBe(false)
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('collapses whitespace when asked, without changing the text', () => {
    const wrapper = mountPane({ preserveWhitespace: false })
    expect(wrapper.classes()).not.toContain('document-text--preserve-whitespace')
    expect(chunkEl('a').textContent).toBe(a.text)
  })

  it('highlights an active passage that continues into the next chunk', () => {
    mountPane({ activeRange: { chunkId: 'a', start: 12, end: a.text.length + 3 } })
    const active = Array.from(document.querySelectorAll<HTMLElement>('.is-active-passage'))
    expect(active.map((s) => [s.closest<HTMLElement>('[data-chunk-id]')!.dataset.chunkId, s.textContent]))
      .toEqual([['a', 'second '], ['b', 'x😀']])
  })

  it('scrolls a chunk or the start of a range into view', () => {
    const scrolled: Element[] = []
    const original = Element.prototype.scrollIntoView
    Element.prototype.scrollIntoView = function (this: Element) { scrolled.push(this) }
    try {
      const wrapper = mountPane({ activeRange: { chunkId: 'b', start: 1, end: 3 } })
      const pane = wrapper.vm as unknown as DocumentTextPaneApi
      pane.scrollToChunk('d')
      pane.scrollToRange({ chunkId: 'b', start: 1, end: 3 })
      // A range starting inside a segment scrolls to that segment.
      pane.scrollToRange({ chunkId: 'a', start: 4, end: 6 })
      pane.scrollToChunk('missing')
      expect(scrolled.map((el) => (el as HTMLElement).dataset.chunkId ?? el.textContent)).toEqual(['d', '😀', a.text])
      expect(pane.root).toBe(wrapper.element)
    } finally {
      Element.prototype.scrollIntoView = original
    }
  })

  it('gives its owner a place at gaps and before each chunk, and classes per chunk', () => {
    const wrapper = mountPane({ chunkClass: (c: TextChunk) => ({ dimmed: c.id === 'b' }) }, {
      gap: ({ paragraph }: { paragraph: { gapAfter: number, gapBefore: number } }) =>
        h('div', { class: 'gap' }, `${paragraph.gapAfter}-${paragraph.gapBefore}`),
      'before-chunk': ({ chunk: c }: { chunk: TextChunk }) => h('span', { class: 'marker' }, `[${c.order}]`)
    })
    expect(wrapper.findAll('.gap').map((g) => g.text())).toEqual(['1-3'])
    expect(wrapper.findAll('.marker').map((m) => m.text())).toEqual(['[0]', '[1]', '[3]'])
    expect(chunkEl('b').classList.contains('dimmed')).toBe(true)
    expect(chunkEl('a').classList.contains('dimmed')).toBe(false)
  })
})

describe('DocumentTextPane with annotations', () => {
  const span: ProjectedSpan = { id: 's1', tagId: 't', start: 0, end: 5, type: 'pos' } as ProjectedSpan
  const annotation = (overrides: Partial<TextPaneAnnotation> = {}): TextPaneAnnotation => ({
    tags: [tag],
    spansFor: (chunkId) => chunkId === 'a' ? [span] : [],
    selectionFor: (chunkId) => chunkId === 'd'
      ? { start: 0, end: 5, showStartHandle: true, showEndHandle: true }
      : null,
    ...overrides
  })

  it('shows the spans and the selection with its handles, and passes on handle drags', async () => {
    const wrapper = mountPane({ annotation: annotation({ highlightSpanId: 's1' }) })
    const tagged = chunkEl('a').querySelector<HTMLElement>('.is-tagged')!
    expect(tagged.textContent).toBe('First')
    expect(tagged.classList.contains('is-highlighted')).toBe(true)
    expect(chunkEl('d').querySelectorAll('.selection-handle')).toHaveLength(2)

    const drag = { chunkId: 'd', handle: 'end', charOffset: 9 }
    wrapper.findAllComponents(ChunkAnnotator)[2].vm.$emit('boundaryDrag', drag)
    expect(wrapper.emitted('boundaryDrag')).toEqual([[drag]])
  })

  it('keeps a chunk\'s span list when other chunks change', async () => {
    const spansOfA = [span]
    const wrapper = mountPane({ annotation: annotation({ spansFor: (id) => id === 'a' ? spansOfA : [] }) })
    const annotatorA = wrapper.findAllComponents(ChunkAnnotator)[0]
    await wrapper.setProps({ annotation: annotation({ spansFor: (id) => id === 'a' ? spansOfA : [], focusTagId: 't' }) })
    expect(annotatorA.props('spans')).toBe(spansOfA)
    expect(annotatorA.props('focusTagId')).toBe('t')
  })
})
