import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { h } from 'vue'

import WrappingBadges from 'src/shared/ui/WrappingBadges.vue'

// Badges clipped after a number of lines with "+N more", expanding in place, within a bounded
// height when asked (#177, #506). The one-line use is covered with the Search classifications.

/** jsdom has no layout: badges from the `perLine`-th on report a lower line. */
function layoutLines (perLine: number) {
  vi.spyOn(HTMLElement.prototype, 'offsetTop', 'get').mockImplementation(function (this: HTMLElement) {
    if (!this.classList.contains('badge')) return 0
    const index = Array.from(this.parentElement?.children ?? []).indexOf(this)
    return Math.floor(index / perLine) * 26
  })
}

const mountBadges = (count: number, props: Record<string, unknown>) => mount(WrappingBadges, {
  props,
  slots: { default: () => Array.from({ length: count }, (_, i) => h('span', { class: 'badge', key: i }, `value ${i}`)) }
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('WrappingBadges', () => {
  it('counts the badges below the shown lines and expands within the bounded height', async () => {
    layoutLines(5)
    const wrapper = mountBadges(100, { lines: 2, expandedLines: 8, badgeHeight: 22 })
    await flushPromises()
    const line = wrapper.find('.wrapping-badges__line')
    const toggle = wrapper.find('button')

    expect(toggle.text()).toBe('+90 more')
    expect([line.classes('collapsed'), line.attributes('style')]).toEqual([true, 'max-height: 48px;'])
    await toggle.trigger('click')
    // Eight lines of 22px with 4px between them, then the badges scroll.
    expect([line.classes('scrolls'), line.attributes('style'), toggle.text()]).toEqual([true, 'max-height: 204px;', 'Show less'])
    expect(toggle.attributes('aria-expanded')).toBe('true')
  })

  it('has no toggle when the badges fit on the shown lines', async () => {
    layoutLines(5)
    const wrapper = mountBadges(10, { lines: 2 })
    await flushPromises()
    expect(wrapper.find('button').exists()).toBe(false)
  })
})
