import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { QBtn, QDialog, QInput, QSelect, Quasar } from 'quasar'

import { ValueKind } from 'src/generated/api'
import FormDialog from 'src/shared/ui/FormDialog.vue'
import AttributeValueDialog from 'src/features/attributes/AttributeValueDialog.vue'

// The form dialogs of attribute definitions (#331): a running save keeps the form open, the
// value dialog offers a special kind only once per attribute, sends only what changed and
// keeps a refusal visible.

const mounted: VueWrapper[] = []
afterEach(() => {
  mounted.splice(0).forEach(w => w.unmount())
  document.body.innerHTML = ''
})

async function open<T> (component: T, props: Record<string, unknown>, slots: Record<string, () => string> = {}) {
  const wrapper = mount(component as never, { props: props as never, slots, global: { plugins: [Quasar] }, attachTo: document.body })
  mounted.push(wrapper)
  ;(wrapper.vm as unknown as { show: () => void }).show()
  await flushPromises()
  return wrapper
}
// A closed dialog reports hide after its leave transition.
const transition = () => new Promise(resolve => setTimeout(resolve, 400))

const button = (wrapper: VueWrapper, label: string) =>
  wrapper.findAllComponents(QBtn).find(b => b.props('label') === label)!

describe('FormDialog', () => {
  it('cannot be closed while a save runs, and closes again afterwards', async () => {
    const wrapper = await open(FormDialog, { dirty: false, okLabel: 'Save', busy: true }, { default: () => 'form' })
    await button(wrapper, 'Cancel').trigger('click')
    // Escape and a click outside reach the form as a shake (no-esc-dismiss, no-backdrop-dismiss).
    wrapper.findComponent(QDialog).vm.$emit('shake')
    await transition()
    expect(wrapper.emitted('hide')).toBeUndefined()
    expect(button(wrapper, 'Cancel').props('disable')).toBe(true)
    expect(button(wrapper, 'Save').props('loading')).toBe(true)

    await wrapper.setProps({ busy: false } as never)
    wrapper.findComponent(QDialog).vm.$emit('shake')
    await transition()
    expect(wrapper.emitted('hide')).toHaveLength(1)
  })
})

describe('AttributeValueDialog', () => {
  it('disables the special kinds the attribute already has', async () => {
    const wrapper = await open(AttributeValueDialog, {
      attributeName: 'speaker', takenKinds: [ValueKind.unknown], save: vi.fn()
    })
    const options = wrapper.findComponent(QSelect).props('options') as { value: ValueKind, disable: boolean }[]
    expect(options.map(o => [o.value, o.disable])).toEqual([
      [ValueKind.value, false], [ValueKind.unknown, true], [ValueKind.notApplicable, false]
    ])
  })

  it('sends only the changed fields of an edited value', async () => {
    const save = vi.fn().mockResolvedValue({ id: 'a1' })
    const wrapper = await open(AttributeValueDialog, {
      attributeName: 'speaker',
      value: { id: 'v1', label: 'politician', description: 'Elected', examples: ['MP'] },
      save
    })
    expect(wrapper.findComponent(QSelect).exists()).toBe(false)
    const inputs = wrapper.findAllComponents(QInput)
    inputs.find(i => i.props('label') === 'Description')!.vm.$emit('update:modelValue', 'Elected or appointed')
    inputs.find(i => i.props('label') === 'Example 1')!.vm.$emit('update:modelValue', 'minister')
    await flushPromises()
    await button(wrapper, 'Save').trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledWith({ description: 'Elected or appointed', examples: ['minister'] })
    expect(wrapper.emitted('ok')).toEqual([[{ id: 'a1' }]])
  })

  it('stays open with the backend message when the save is refused', async () => {
    const save = vi.fn().mockRejectedValue(new Error('politician already exists'))
    const wrapper = await open(AttributeValueDialog, { attributeName: 'speaker', save })
    wrapper.findAllComponents(QInput).find(i => i.props('label') === 'Label')!.vm.$emit('update:modelValue', 'politician')
    await flushPromises()
    await button(wrapper, 'Add').trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledWith({ label: 'politician', kind: ValueKind.value, description: '', examples: [] })
    expect(wrapper.emitted('ok')).toBeUndefined()
    expect(document.querySelector('[data-testid="value-dialog-error"]')?.textContent).toContain('politician already exists')
  })
})
