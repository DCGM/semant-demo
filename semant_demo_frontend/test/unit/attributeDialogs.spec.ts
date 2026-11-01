import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { QBtn, QCheckbox, QDialog, QInput, QOptionGroup, QSelect, Quasar } from 'quasar'

import { Cardinality, ValueKind, type Attribute } from 'src/generated/api'
import FormDialog from 'src/shared/ui/FormDialog.vue'
import AttributeDialog from 'src/features/attributes/AttributeDialog.vue'
import AttributeValueDialog from 'src/features/attributes/AttributeValueDialog.vue'
import { AttributeWriteError } from 'src/features/attributes/attributesStore'

// The form dialogs of attribute definitions (#331, #506): a running save keeps the form open
// and freezes everything that goes into its request, a refusal stays visible with what was
// typed, Unknown / Not applicable are fixed checkboxes, the cardinality is fixed once created,
// All tags is sent explicitly and Selected tags with none chosen is no tag (#522), and in Edit each value change saves at
// once while Save sends only the attribute's own fields.

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

/** A promise settled from the test. */
function deferred<T> () {
  let settle!: { resolve: (value: T) => void, reject: (e: unknown) => void }
  const promise = new Promise<T>((resolve, reject) => { settle = { resolve, reject } })
  return { promise, resolve: (value: T) => settle.resolve(value), reject: (e: unknown) => settle.reject(e) }
}

const button = (wrapper: VueWrapper, label: string) =>
  wrapper.findAllComponents(QBtn).find(b => b.props('label') === label || b.attributes('aria-label') === label)!
const input = (wrapper: VueWrapper, label: string) =>
  wrapper.findAllComponents(QInput).find(i => i.props('label') === label)!
const checkbox = (wrapper: VueWrapper, label: string) =>
  wrapper.findAllComponents(QCheckbox).find(c => c.props('label') === label)!
const type = async (wrapper: VueWrapper, label: string, text: string) => {
  input(wrapper, label).vm.$emit('update:modelValue', text)
  await flushPromises()
}
const text = (testid: string) => document.querySelector(`[data-testid="${testid}"]`)?.textContent ?? ''

const tags = () => [{ id: 't1', name: 'Person' }, { id: 't2', name: 'Place' }] as never
const speaker = (extra: Partial<Attribute> = {}): Attribute => ({
  id: 'a1',
  name: 'Speaker',
  description: '',
  cardinality: Cardinality.single,
  tagIds: ['t1'],
  revision: 1,
  values: [{ id: 'v1', label: 'politician' }, { id: 'v2', label: 'journalist' }],
  ...extra
})
const valueActions = (overrides: Record<string, unknown> = {}) => ({
  addValue: vi.fn(),
  updateValue: vi.fn(),
  setSpecialValue: vi.fn(),
  ...overrides
})

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

  it('waits for a write that saves on its own before it can be sent or closed', async () => {
    const wrapper = await open(FormDialog, { dirty: false, okLabel: 'Save', pending: true }, { default: () => 'form' })
    wrapper.findComponent(QDialog).vm.$emit('shake')
    await transition()
    expect(wrapper.emitted('hide')).toBeUndefined()
    expect([button(wrapper, 'Save').props('disable'), button(wrapper, 'Save').props('loading')]).toEqual([true, false])
  })
})

describe('AttributeValueDialog', () => {
  it('sends only the changed fields of an edited value', async () => {
    const save = vi.fn().mockResolvedValue({ id: 'a1' })
    const wrapper = await open(AttributeValueDialog, {
      attributeName: 'speaker',
      value: { id: 'v1', label: 'politician', description: 'Elected', examples: ['MP'] },
      save
    })
    await type(wrapper, 'Description', 'Elected or appointed')
    await type(wrapper, 'Example 1', 'minister')
    await button(wrapper, 'Save').trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledWith({ description: 'Elected or appointed', examples: ['minister'] })
    expect(wrapper.emitted('ok')).toEqual([[{ id: 'a1' }]])
  })

  it('freezes the form while saving, then keeps the refusal and what was typed', async () => {
    const answer = deferred<never>()
    const save = vi.fn().mockReturnValue(answer.promise)
    const wrapper = await open(AttributeValueDialog, { attributeName: 'speaker', save })
    await type(wrapper, 'Label', 'politician')
    await type(wrapper, 'Description', 'Holds an office.')
    await button(wrapper, 'Add').trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledWith({ label: 'politician', description: 'Holds an office.', examples: [] })
    expect(wrapper.findAllComponents(QInput).map(i => i.props('disable'))).toEqual([true, true, true])
    expect([button(wrapper, 'Add example').props('disable'), button(wrapper, 'Remove example 1').props('disable')]).toEqual([true, true])

    answer.reject(new Error('politician already exists'))
    await flushPromises()
    expect(wrapper.emitted('ok')).toBeUndefined()
    expect(text('value-dialog-error')).toContain('politician already exists')
    expect(input(wrapper, 'Label').props('modelValue')).toBe('politician')
    expect(input(wrapper, 'Label').props('disable')).toBe(false)
  })
})

describe('Create Attribute', () => {
  it('sends the values with the fixed special ones and warns that multiple values are for good', async () => {
    const save = vi.fn().mockResolvedValue({ id: 'a9' })
    const wrapper = await open(AttributeDialog, { tags, save })
    await type(wrapper, 'Name', 'Topic')
    await type(wrapper, 'Value 1', ' economy ')
    expect(text('attribute-multiple-warning')).toBe('')
    checkbox(wrapper, 'Allow multiple values per annotation').vm.$emit('update:modelValue', true)
    checkbox(wrapper, 'Allow Not applicable').vm.$emit('update:modelValue', true)
    await flushPromises()
    expect(text('attribute-multiple-warning')).toContain('cannot be reversed')

    await button(wrapper, 'Create').trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledWith({
      name: 'Topic',
      description: '',
      cardinality: Cardinality.multi,
      allTags: true,
      tagIds: [],
      values: [{ label: 'economy' }, { label: 'Not applicable', kind: ValueKind.notApplicable }]
    })
  })

  it('sends Selected tags without a tag as no tag, never as All tags', async () => {
    const save = vi.fn().mockResolvedValue({ id: 'a9' })
    const wrapper = await open(AttributeDialog, { tags, save })
    await type(wrapper, 'Name', 'Mood')
    wrapper.findComponent(QOptionGroup).vm.$emit('update:modelValue', 'selected')
    await flushPromises()
    expect(document.body.textContent).toContain('No tags: no annotation can take values of this attribute.')
    await button(wrapper, 'Create').trigger('click')
    await flushPromises()
    expect(save).toHaveBeenLastCalledWith(expect.objectContaining({ allTags: false, tagIds: [] }))
  })

  it('sends the selected tags with All tags off', async () => {
    const save = vi.fn().mockResolvedValue({ id: 'a9' })
    const wrapper = await open(AttributeDialog, { tags, save })
    await type(wrapper, 'Name', 'Mood')
    wrapper.findComponent(QOptionGroup).vm.$emit('update:modelValue', 'selected')
    await flushPromises()
    wrapper.findComponent(QSelect).vm.$emit('update:modelValue', ['t2'])
    await flushPromises()
    await button(wrapper, 'Create').trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ allTags: false, tagIds: ['t2'] }))
  })

  it('freezes every field while saving and keeps them after a failure', async () => {
    const answer = deferred<never>()
    const wrapper = await open(AttributeDialog, { tags, save: vi.fn().mockReturnValue(answer.promise) })
    await type(wrapper, 'Name', 'Topic')
    await type(wrapper, 'Value 1', 'economy')
    await button(wrapper, 'Create').trigger('click')
    await flushPromises()
    expect(wrapper.findAllComponents(QInput).every(i => i.props('disable'))).toBe(true)
    expect(wrapper.findAllComponents(QCheckbox).every(c => c.props('disable'))).toBe(true)
    expect(wrapper.findComponent(QOptionGroup).props('disable')).toBe(true)
    expect([button(wrapper, 'Add value').props('disable'), button(wrapper, 'Remove value 1').props('disable')]).toEqual([true, true])

    answer.reject(new AttributeWriteError('Topic already exists', 400))
    await flushPromises()
    expect(text('attribute-dialog-error')).toContain('Topic already exists')
    expect([input(wrapper, 'Name').props('modelValue'), input(wrapper, 'Value 1').props('modelValue')]).toEqual(['Topic', 'economy'])
    expect(input(wrapper, 'Name').props('disable')).toBe(false)
  })
})

describe('Edit Attribute', () => {
  it('shows the cardinality read-only and sends only the changed fields', async () => {
    const save = vi.fn().mockResolvedValue(speaker({ name: 'Speaker type', revision: 2 }))
    const wrapper = await open(AttributeDialog, { attribute: speaker(), tags, save, valueActions: valueActions() })
    const cardinality = checkbox(wrapper, 'Allow multiple values per annotation')
    expect([cardinality.props('modelValue'), cardinality.props('disable')]).toEqual([false, true])
    expect(text('attribute-cardinality')).toContain('cannot be changed after the attribute is created')
    await type(wrapper, 'Name', 'Speaker type')
    await button(wrapper, 'Save').trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledWith({ name: 'Speaker type' })
  })

  it('saves a value change at once, and Save waits for it', async () => {
    const answer = deferred<Attribute>()
    const setSpecialValue = vi.fn().mockReturnValue(answer.promise)
    const save = vi.fn()
    const wrapper = await open(AttributeDialog, { attribute: speaker(), tags, save, valueActions: valueActions({ setSpecialValue }) })
    expect(text('attribute-values-immediate')).toContain('saved immediately')

    checkbox(wrapper, 'Allow Unknown').vm.$emit('update:modelValue', true)
    await flushPromises()
    expect(setSpecialValue).toHaveBeenCalledWith(speaker(), ValueKind.unknown, true)
    expect(button(wrapper, 'Save').props('disable')).toBe(true)
    expect(input(wrapper, 'Name').props('disable')).toBe(true)

    answer.resolve(speaker({ revision: 2, values: [...speaker().values!, { id: 'u1', label: 'Unknown', kind: ValueKind.unknown }] }))
    await flushPromises()
    expect(checkbox(wrapper, 'Allow Unknown').props('modelValue')).toBe(true)
    expect(button(wrapper, 'Save').props('disable')).toBe(false)
    // Only Unknown changed, and it is saved: Save has nothing to send and closes.
    await button(wrapper, 'Save').trigger('click')
    await flushPromises()
    expect(save).not.toHaveBeenCalled()
    expect(wrapper.emitted('ok')).toEqual([[null]])
  })

  it('keeps a failed value change visible and changes nothing', async () => {
    const updateValue = vi.fn().mockRejectedValue(new AttributeWriteError('The value could not be saved.', null))
    const wrapper = await open(AttributeDialog, { attribute: speaker(), tags, save: vi.fn(), valueActions: valueActions({ updateValue }) })
    await button(wrapper, 'Retire journalist').trigger('click')
    await flushPromises()
    expect(updateValue).toHaveBeenCalledWith('v2', { retired: true })
    expect(text('attribute-values-error')).toContain('The value could not be saved.')
    expect(button(wrapper, 'Retire journalist').exists()).toBe(true)
  })

  it('finds values by label, within a bounded list', async () => {
    const values = Array.from({ length: 100 }, (_, i) => ({ id: `v${i}`, label: `topic ${i}` }))
    const wrapper = await open(AttributeDialog, { attribute: speaker({ values }), tags, save: vi.fn(), valueActions: valueActions() })
    expect(document.querySelectorAll('[data-testid="attribute-dialog-value-row"]')).toHaveLength(100)
    wrapper.findAllComponents(QInput).find(i => i.vm.$attrs.placeholder === 'Search values')!.vm.$emit('update:modelValue', 'topic 9')
    await flushPromises()
    const rows = Array.from(document.querySelectorAll('[data-testid="attribute-dialog-value-label"]')).map(r => r.textContent)
    expect(rows).toEqual(['topic 9', ...Array.from({ length: 10 }, (_, i) => `topic 9${i}`)])
    expect(document.querySelector('[data-testid="attribute-dialog-value-label"] mark')?.textContent).toBe('topic 9')
  })

  it('freezes the values while the attribute saves', async () => {
    const answer = deferred<Attribute>()
    const wrapper = await open(AttributeDialog, {
      attribute: speaker(), tags, save: vi.fn().mockReturnValue(answer.promise), valueActions: valueActions()
    })
    await type(wrapper, 'Name', 'Speaker type')
    await button(wrapper, 'Save').trigger('click')
    await flushPromises()
    expect([button(wrapper, 'Retire politician').props('disable'), button(wrapper, 'Add value').props('disable'),
      checkbox(wrapper, 'Allow Unknown').props('disable')]).toEqual([true, true, true])
    answer.resolve(speaker({ name: 'Speaker type', revision: 2 }))
    await flushPromises()
    expect(wrapper.emitted('ok')).toHaveLength(1)
  })

  it('shows a refused narrowing of the tags at the tags and keeps them', async () => {
    const message = '1 annotations with values of this attribute have a tag outside the new applicable tags; change or remove those values first.'
    const save = vi.fn().mockRejectedValue(new AttributeWriteError(message, 409))
    const wrapper = await open(AttributeDialog, { attribute: speaker(), tags, save, valueActions: valueActions() })
    wrapper.findComponent(QSelect).vm.$emit('update:modelValue', ['t2'])
    await flushPromises()
    await button(wrapper, 'Save').trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledWith({ allTags: false, tagIds: ['t2'] })
    const select = wrapper.findComponent(QSelect)
    expect([select.props('error'), select.props('errorMessage'), select.props('modelValue')]).toEqual([true, message, ['t2']])
    expect(text('attribute-dialog-error')).toBe('')
    expect(wrapper.emitted('ok')).toBeUndefined()
  })

  it('keeps Selected tags when the last tag is removed, and changes the scope only explicitly', async () => {
    const save = vi.fn().mockResolvedValue(speaker())
    const wrapper = await open(AttributeDialog, { attribute: speaker(), tags, save, valueActions: valueActions() })
    wrapper.findComponent(QSelect).vm.$emit('update:modelValue', [])
    await flushPromises()
    await button(wrapper, 'Save').trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledWith({ allTags: false, tagIds: [] })

    // An attribute for no tag opens as Selected tags with none; for all tags as All tags.
    const none = await open(AttributeDialog, { attribute: speaker({ tagIds: [] }), tags, save, valueActions: valueActions() })
    expect(none.findComponent(QOptionGroup).props('modelValue')).toBe('selected')
    const everywhere = await open(AttributeDialog, {
      attribute: speaker({ allTags: true, tagIds: [] }), tags, save, valueActions: valueActions()
    })
    expect(everywhere.findComponent(QOptionGroup).props('modelValue')).toBe('all')
    everywhere.findComponent(QOptionGroup).vm.$emit('update:modelValue', 'selected')
    await flushPromises()
    await button(everywhere, 'Save').trigger('click')
    await flushPromises()
    expect(save).toHaveBeenLastCalledWith({ allTags: false, tagIds: [] })
  })
})
