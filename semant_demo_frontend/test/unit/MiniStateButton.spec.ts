import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { Quasar } from 'quasar'

import MiniStateButton from 'src/components/MiniStateButton.vue'

function mountButton (drawerMiniState: boolean) {
  return mount(MiniStateButton, {
    props: { drawerMiniState },
    // The client ESM build of Quasar registers all of its components.
    global: { plugins: [[Quasar, {}]] }
  })
}

describe('MiniStateButton', () => {
  it.each([
    [true, 'chevron_right'],
    [false, 'chevron_left']
  ])('shows the expand/collapse icon for drawerMiniState=%s', (miniState, icon) => {
    const wrapper = mountButton(miniState)

    expect(wrapper.find('button').text()).toContain(icon)
  })

  it('emits click when pressed', async () => {
    vi.spyOn(console, 'log').mockImplementation(() => undefined)
    const wrapper = mountButton(false)

    await wrapper.find('button').trigger('click')

    expect(wrapper.emitted('click')).toHaveLength(1)
  })
})
