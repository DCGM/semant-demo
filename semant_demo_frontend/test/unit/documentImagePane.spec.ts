import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { Quasar } from 'quasar'

import DocumentImagePane from 'src/features/documents/scan/DocumentImagePane.vue'
import ScanPageView from 'src/features/documents/scan/ScanPageView.vue'

// The scan pane in jsdom: which page, layout and state it shows, which requests it sends,
// and its keyboard contract. Geometry and the real pointer/zoom behavior are covered by
// scanGeometry.spec.ts and the browser test (test/e2e/scanViewer.spec.ts).

const DOC = 'doc-1'
const page = (n: number, extra: Record<string, unknown> = {}) => ({
  page_id: `p${n}`,
  order: n,
  label: String(n),
  page_type: 'NormalPage',
  width: 1000,
  height: 1400,
  image_url: `/api/documents/${DOC}/pages/p${n}/image`,
  layout_url: `/api/documents/${DOC}/pages/p${n}/layout`,
  thumbnail_url: `/api/documents/${DOC}/pages/p${n}/thumbnail`,
  ...extra
})
const MANIFEST = {
  document_id: DOC,
  available: true,
  pages: [page(0, { label: '[1]', page_type: 'FrontCover', layout_url: null }), page(1), page(2), page(3, { image_url: null, layout_url: null, thumbnail_url: null })]
}
const layoutFile = (pageId: string, lines = 3) => ({
  schema: 'semant.page-layout',
  version: 1,
  pageId,
  image: { width: 1000, height: 1400 },
  regions: [{
    id: 'r1',
    lines: Array.from({ length: lines }, (_, i) => ({
      id: `${pageId}-l${i + 1}`,
      text: `Line ${i + 1} of ${pageId}`,
      baseline: [[100, 200 + i * 60], [800, 200 + i * 60]],
      heights: [24, 8]
    }))
  }]
})

type Call = { url: URL, signal?: AbortSignal | null, answer: (body: unknown, status?: number) => void }

function controlledFetch () {
  const calls: Call[] = []
  const fetchMock = vi.fn((input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => new Promise<Response>((resolve, reject) => {
    const abort = () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' }))
    if (init?.signal?.aborted) abort()
    init?.signal?.addEventListener('abort', abort)
    calls.push({
      url: new URL(String(input)),
      signal: init?.signal,
      answer: (body, status = 200) => resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
    })
  }))
  return { calls, fetchMock }
}

describe('DocumentImagePane', () => {
  const originalFetch = globalThis.fetch
  let calls: Call[]
  let wrapper: VueWrapper | null = null

  beforeEach(() => {
    const controlled = controlledFetch()
    calls = controlled.calls
    globalThis.fetch = controlled.fetchMock as typeof fetch
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    globalThis.fetch = originalFetch
  })

  /** The latest request to `path`. */
  const callTo = (path: string) => [...calls].reverse().find(c => c.url.pathname === path)

  async function open (props: Record<string, unknown> = {}) {
    wrapper = mount(DocumentImagePane, {
      props: { documentId: DOC, ...props },
      global: { plugins: [[Quasar, {}]] },
      attachTo: document.body
    })
    await flushPromises()
    callTo(`/api/documents/${DOC}/pages`)!.answer(MANIFEST)
    await flushPromises()
    return wrapper
  }

  async function answerLayout (pageId: string, lines = 3) {
    callTo(`/api/documents/${DOC}/pages/${pageId}/layout`)!.answer(layoutFile(pageId, lines))
    await flushPromises()
  }

  function loadImage (w: VueWrapper) {
    w.find('img.scan-view__image').element.dispatchEvent(new Event('load'))
  }

  const press = async (w: VueWrapper, key: string, target = '[data-testid="scan-viewport"]') => {
    await w.find(target).trigger('keydown', { key })
    await flushPromises()
  }

  it('opens the requested page and reads only its layout', async () => {
    const w = await open({ pageId: 'p2' })
    const emitted = w.emitted('pageChange')!
    expect(emitted[0][1]).toBe(2)
    expect(calls.map(c => c.url.pathname)).toEqual([`/api/documents/${DOC}/pages`, `/api/documents/${DOC}/pages/p2/layout`])
    expect(w.find('[data-testid="page-position"]').text()).toBe('3 / 4')
    expect(w.find('img.scan-view__image').attributes('src')).toMatch(/\/api\/documents\/doc-1\/pages\/p2\/image$/)
  })

  it('says when a document has no scans, and when a page has none or no lines', async () => {
    wrapper = mount(DocumentImagePane, { props: { documentId: DOC }, global: { plugins: [[Quasar, {}]] } })
    await flushPromises()
    calls[0].answer({ document_id: DOC, available: false, pages: [] })
    await flushPromises()
    expect(wrapper.find('[data-testid="image-pane-text-only"]').exists()).toBe(true)
    expect(wrapper.emitted('loaded')![0][0]).toEqual({ available: false, pageCount: 0, pages: [] })
    wrapper.unmount()

    const w = await open({ pageId: 'p0' })
    // The cover has a scan but no layout file: no layout request, a notice.
    expect(calls.filter(c => c.url.pathname.endsWith('/layout'))).toHaveLength(0)
    expect(w.find('[data-testid="layout-notice"]').text()).toContain('No text lines')
    await w.setProps({ pageId: 'p3' })
    await flushPromises()
    expect(w.find('[data-testid="no-scan"]').exists()).toBe(true)
  })

  it('reports a manifest failure with a retry', async () => {
    wrapper = mount(DocumentImagePane, { props: { documentId: DOC }, global: { plugins: [[Quasar, {}]] } })
    await flushPromises()
    calls[0].answer({ detail: 'Document with id doc-1 not found' }, 404)
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toContain('not found')
    await wrapper.find('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(calls).toHaveLength(2)
  })

  it('never shows the lines of a page left before its layout arrived', async () => {
    const w = await open({ pageId: 'p1' })
    const first = callTo(`/api/documents/${DOC}/pages/p1/layout`)!
    await w.find('[aria-label="Next page"]').trigger('click')
    await flushPromises()
    // The obsolete request was cancelled.
    expect(first.signal?.aborted).toBe(true)
    first.answer(layoutFile('p1'))
    await answerLayout('p2', 2)
    loadImage(w)
    await flushPromises()
    const ids = w.findAll('polygon.scan-line').map(p => p.attributes('data-line-id'))
    expect(ids).toEqual(['p2-l1', 'p2-l2'])
  })

  it('keeps the page keys: Up/Down lines, PageUp/PageDown pages, +/- and 0 zoom', async () => {
    const w = await open({ pageId: 'p1' })
    await answerLayout('p1')
    loadImage(w)
    await flushPromises()

    await press(w, 'ArrowDown')
    await press(w, 'ArrowDown')
    expect(w.emitted('lineFocus')!.map(e => e[0])).toEqual([
      { pageId: 'p1', lineId: 'p1-l1' }, { pageId: 'p1', lineId: 'p1-l2' }
    ])
    expect(w.find('polygon.scan-line--active').attributes('data-line-id')).toBe('p1-l2')
    expect(w.find('[data-testid="line-announcement"]').text()).toBe('Line 2 of 3: Line 2 of p1')
    await press(w, 'ArrowUp')
    expect(w.emitted('lineFocus')!.at(-1)![0]).toEqual({ pageId: 'p1', lineId: 'p1-l1' })

    const view = w.findComponent(ScanPageView)
    const zoom = () => Number(w.find('[data-testid="zoom-level"]').text().replace('%', ''))
    const before = zoom()
    await press(w, '+')
    expect(zoom()).toBeGreaterThan(before)
    await press(w, '-')
    await press(w, '-')
    expect(zoom()).toBeLessThan(before)
    await press(w, '0')
    expect((view.vm as unknown as { view: () => { fitted: boolean } }).view().fitted).toBe(true)

    await press(w, 'PageDown')
    expect(w.emitted('update:pageId')!.at(-1)![0]).toBe('p2')
    await press(w, 'PageUp')
    expect(w.emitted('update:pageId')!.at(-1)![0]).toBe('p1')
  })

  it('leaves the keys of the page field and of modified shortcuts alone', async () => {
    const w = await open({ pageId: 'p1' })
    await answerLayout('p1')
    const changes = () => w.emitted('update:pageId')!.length
    const before = changes()
    await press(w, 'PageDown', '.image-pane__jump input')
    await press(w, '0', '.image-pane__jump input')
    await w.find('[data-testid="scan-viewport"]').trigger('keydown', { key: 'PageDown', ctrlKey: true })
    expect(changes()).toBe(before)
    expect(w.find('[data-testid="page-position"]').text()).toBe('2 / 4')
  })

  it('jumps to a printed label or position and explains an unknown page', async () => {
    const w = await open()
    const input = w.find('.image-pane__jump input')
    await input.setValue('9')
    await w.find('form').trigger('submit')
    expect(w.text()).toContain('No page "9"')
    await input.setValue('[1]')
    await w.find('form').trigger('submit')
    await input.setValue('2')
    await w.find('form').trigger('submit')
    await flushPromises()
    // The first page on opening, then the page labelled "2" ("[1]" is shown already).
    expect(w.emitted('update:pageId')!.map(e => e[0])).toEqual(['p0', 'p2'])
  })

  it('reports a clicked line by its source ids', async () => {
    const w = await open({ pageId: 'p1' })
    await answerLayout('p1')
    loadImage(w)
    await flushPromises()
    w.findComponent(ScanPageView).vm.$emit('lineClick', { lineId: 'p1-l3' })
    await flushPromises()
    expect(w.emitted('lineSelect')![0][0]).toEqual({ pageId: 'p1', lineId: 'p1-l3' })
    expect(w.find('polygon.scan-line--active').attributes('data-line-id')).toBe('p1-l3')
  })

  it('answers focus requests for other pages, and drops one that a newer request replaced', async () => {
    const w = await open({ pageId: 'p1' })
    await answerLayout('p1')
    const pane = w.vm as unknown as { focus: (r: object) => Promise<boolean> }
    const older = pane.focus({ pageId: 'p2', lineIds: ['p2-l1'] })
    await flushPromises()
    const newer = pane.focus({ pageId: 'p1', lineIds: ['p1-l2'] })
    await flushPromises()
    await answerLayout('p1')
    expect(await older).toBe(false)
    expect(await newer).toBe(true)
    expect(w.emitted('update:pageId')!.at(-1)![0]).toBe('p1')
    loadImage(w)
    await flushPromises()
    expect(w.find('polygon.scan-line--active').attributes('data-line-id')).toBe('p1-l2')
    expect(await pane.focus({ pageId: 'unknown', lineIds: ['x'] })).toBe(false)
  })

  it('answers a focus request sent while the layout of the page is still loading', async () => {
    const w = await open({ pageId: 'p1' })
    const pane = w.vm as unknown as { focus: (r: object) => Promise<boolean> }
    const request = pane.focus({ pageId: 'p1', lineIds: ['p1-l3'] })
    await flushPromises()
    await answerLayout('p1')
    expect(await request).toBe(true)
    expect(calls.filter(c => c.url.pathname.endsWith('/layout'))).toHaveLength(1)
    loadImage(w)
    await flushPromises()
    expect(w.find('polygon.scan-line--active').attributes('data-line-id')).toBe('p1-l3')
  })
})
