import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { Quasar } from 'quasar'

import MiniStateButton from 'src/components/MiniStateButton.vue'

function mountButton (drawerMiniState: boolean, side?: 'left' | 'right') {
  return mount(MiniStateButton, {
    props: { drawerMiniState, side },
    // The client ESM build of Quasar registers all of its components.
    global: { plugins: [[Quasar, {}]] }
  })
}

describe('MiniStateButton', () => {
  it.each([
    [true, undefined, 'keyboard_double_arrow_right', 'Expand navigation'],
    [false, undefined, 'keyboard_double_arrow_left', 'Collapse navigation'],
    [true, 'right', 'keyboard_double_arrow_left', 'Expand sidebar'],
    [false, 'right', 'keyboard_double_arrow_right', 'Collapse sidebar']
  ] as const)('drawerMiniState=%s side=%s shows %s labelled %s', (miniState, side, icon, label) => {
    const button = mountButton(miniState, side).find('button')

    expect(button.text()).toContain(icon)
    expect(button.attributes('aria-label')).toBe(label)
    expect(button.attributes('aria-expanded')).toBe(String(!miniState))
  })

  // #253: a mini-state toggle must not look like a (blue) back arrow.
  it('does not use back-arrow icons or the primary color', () => {
    for (const miniState of [true, false]) {
      const button = mountButton(miniState).find('button')
      expect(button.text()).not.toMatch(/\b(chevron_left|arrow_back)\b/)
      expect(button.classes()).not.toContain('bg-primary')
    }
  })

  it('emits click when pressed', async () => {
    const wrapper = mountButton(false)

    await wrapper.find('button').trigger('click')

    expect(wrapper.emitted('click')).toHaveLength(1)
  })
})
