import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { Quasar } from 'quasar'

import DocumentWorkspace from 'src/features/documents/workspace/DocumentWorkspace.vue'
import WorkspaceModeToggle from 'src/features/documents/workspace/WorkspaceModeToggle.vue'
import { fillHeight } from 'src/features/documents/workspace/fillHeight'
import {
  DEFAULT_TEXT_SHARE, SPLIT_STORAGE_KEY, clampShare, readShare, shareAt, shareBounds
} from 'src/features/documents/workspace/splitRatio'

// The layout of the document workspace (#600): the scan on the left and the text on the right,
// a divider dragged or moved by keys between them, its split remembered in this browser, and
// the views filling the window's height.

// A workspace 1208 px wide: 1200 px for the panes beside the 8 px divider.
const WIDTH = 1208
const ROOM = WIDTH - 8

describe('the split between the text and the scan', () => {
  it('keeps both panes at their minimum width', () => {
    expect(shareBounds(WIDTH)).toEqual({ min: 360 / ROOM, max: 1 - 300 / ROOM })
    expect(clampShare(0.1, WIDTH)).toBe(360 / ROOM)
    expect(clampShare(0.95, WIDTH)).toBe(1 - 300 / ROOM)
    expect(clampShare(0.5, WIDTH)).toBe(0.5)
    // Too narrow for both minimums (the workspace shows one pane then): an even split.
    expect(shareBounds(500)).toEqual({ min: 0.5, max: 0.5 })
  })

  it('gives the text the width right of the divider', () => {
    // The divider's centre 4 px right of the scan's 600 px: the text has the other 600 px.
    expect(shareAt(604, WIDTH)).toBeCloseTo(0.5)
    expect(shareAt(304, WIDTH)).toBeCloseTo(0.75)
    expect(shareAt(10, WIDTH)).toBe(1 - 300 / ROOM)
  })

  it('reads a remembered share, else the default', () => {
    localStorage.removeItem(SPLIT_STORAGE_KEY)
    expect(readShare()).toBe(DEFAULT_TEXT_SHARE)
    localStorage.setItem(SPLIT_STORAGE_KEY, '0.4')
    expect(readShare()).toBe(0.4)
    for (const bad of ['', 'wide', '0', '1', '-0.2', '3']) {
      localStorage.setItem(SPLIT_STORAGE_KEY, bad)
      expect(readShare()).toBe(DEFAULT_TEXT_SHARE)
    }
    localStorage.removeItem(SPLIT_STORAGE_KEY)
  })
})

describe('DocumentWorkspace layout', () => {
  // jsdom lays nothing out: every element is WIDTH wide (shadowing Element's clientWidth).
  beforeEach(() => {
    localStorage.removeItem(SPLIT_STORAGE_KEY)
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, get: () => WIDTH })
  })

  afterEach(() => {
    delete (HTMLElement.prototype as { clientWidth?: number }).clientWidth
    localStorage.removeItem(SPLIT_STORAGE_KEY)
    document.body.innerHTML = ''
  })

  const mountWorkspace = (mode: 'split' | 'text' | 'scan' = 'split') => mount(DocumentWorkspace, {
    props: { documentId: 'd1', mode },
    slots: { default: '<p class="the-text">Text</p>' },
    global: { plugins: [Quasar], stubs: { DocumentImagePane: { template: '<div class="the-scan" />' } } },
    attachTo: document.body
  })

  const divider = (wrapper: ReturnType<typeof mountWorkspace>) => wrapper.get('[data-testid="workspace-divider"]')
  const share = (wrapper: ReturnType<typeof mountWorkspace>) => Number(divider(wrapper).attributes('aria-valuenow'))

  it('shows the scan, the divider and the text from left to right, in the reading order too', () => {
    const wrapper = mountWorkspace()
    const panes = Array.from(wrapper.element.children).map(el => (el as HTMLElement).dataset.testid)
    expect(panes).toEqual(['workspace-scan', 'workspace-divider', 'workspace-text'])
    expect(wrapper.get('[data-testid="workspace-text"]').find('.the-text').exists()).toBe(true)
    expect(divider(wrapper).attributes('aria-controls')).toBe(wrapper.get('[data-testid="workspace-text"]').attributes('id'))
  })

  it('has a divider only with both panes', () => {
    expect(mountWorkspace('text').find('[data-testid="workspace-divider"]').exists()).toBe(false)
    expect(mountWorkspace('scan').find('[data-testid="workspace-divider"]').exists()).toBe(false)
  })

  it('starts at the remembered share, else 55 % for the text', () => {
    expect(share(mountWorkspace())).toBe(55)
    localStorage.setItem(SPLIT_STORAGE_KEY, '0.62')
    expect(share(mountWorkspace())).toBe(62)
  })

  it('moves the divider with the arrow keys, within the minimum widths, and remembers it', async () => {
    const wrapper = mountWorkspace()
    await divider(wrapper).trigger('keydown', { key: 'ArrowLeft' })
    expect(share(wrapper)).toBe(57) // the divider moves left: the text, on its right, grows
    await divider(wrapper).trigger('keydown', { key: 'ArrowRight', shiftKey: true })
    expect(share(wrapper)).toBe(47)
    expect(Number(localStorage.getItem(SPLIT_STORAGE_KEY))).toBeCloseTo(0.47)
    await divider(wrapper).trigger('keydown', { key: 'Home' })
    expect(share(wrapper)).toBe(Math.round(360 / ROOM * 100))
    await divider(wrapper).trigger('keydown', { key: 'End' })
    expect(share(wrapper)).toBe(Math.round((1 - 300 / ROOM) * 100))
    expect(divider(wrapper).attributes('aria-valuemax')).toBe(String(share(wrapper)))
    await divider(wrapper).trigger('dblclick')
    expect(share(wrapper)).toBe(55)
  })

  it('leaves other keys alone', async () => {
    const wrapper = mountWorkspace()
    await divider(wrapper).trigger('keydown', { key: 'Tab' })
    expect(share(wrapper)).toBe(55)
    expect(localStorage.getItem(SPLIT_STORAGE_KEY)).toBeNull()
  })
})

describe('the view toggle', () => {
  const labels = (narrow: boolean) => mount(WorkspaceModeToggle, {
    props: { modelValue: 'split', narrow },
    global: { plugins: [Quasar] }
  }).findAll('button').map(b => b.text())

  it('lists the views in the order of the panes', () => {
    expect(labels(false)).toEqual(['imageScan', 'vertical_splitText and scan', 'articleText'])
    expect(labels(true)).toEqual(['imageScan', 'articleText'])
  })
})

describe('the document views', () => {
  it('are exactly as tall as the room under the header', () => {
    expect(fillHeight(64, 900)).toEqual({ height: '836px' })
    expect(fillHeight(64, 40)).toEqual({ height: '0px' })
  })
})
