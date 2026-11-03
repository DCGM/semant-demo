import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { QBtn, QInput, QToggle, Quasar } from 'quasar'

import { Cardinality, ResponseError, type Attribute, type PatchAttribute, type Tag } from 'src/generated/api'
import TagsDialog from 'src/features/annotations/TagsDialog.vue'

// Create/Edit Tag with its applicable attributes (#516): a Selected tags attribute is switched
// for this tag only (adding or removing just this tag, also the last one), an All tags one is on
// and locked, retired ones are not offered. The dialog saves the tag, then each switched
// attribute, and closes only when all are saved; a failed attribute change keeps the saved tag
// (Create becomes Edit), shows the message at that attribute and is the only one Save sends again;
// closing it then is no confirmation.

const listed = vi.fn<[string], Promise<Attribute[]>>()
const updated = vi.fn<[string, string, PatchAttribute], Promise<Attribute>>()

vi.mock('src/features/attributes/useAttributesRepository', () => ({
  useAttributesRepository: () => ({
    getAll: (collectionId: string) => listed(collectionId),
    update: (collectionId: string, attributeId: string, patch: PatchAttribute) => updated(collectionId, attributeId, patch)
  })
}))

const attribute = (id: string, name: string, extra: Partial<Attribute> = {}): Attribute =>
  ({ id, name, cardinality: Cardinality.single, revision: 1, values: [], tagIds: [], ...extra })
const speaker = attribute('a1', 'speaker_type', { tagIds: ['t1'] })
const mood = attribute('a2', 'mood')
const topic = attribute('a3', 'topic', { allTags: true })
const old = attribute('a4', 'old', { tagIds: ['t1'], retired: true })

const person: Tag = { id: 't1', name: 'Person', shorthand: 'P', color: '#1976d2', pictogram: 'label', definition: '', examples: [] } as Tag
const created: Tag = { ...person, id: 't9', name: 'Speaker', shorthand: 'S' }

/** The attribute as a write of `patch` leaves it. */
function applied (attr: Attribute, patch: PatchAttribute): Attribute {
  const kept = (attr.tagIds ?? []).filter(id => !(patch.removeTagIds ?? []).includes(id))
  return { ...attr, tagIds: [...kept, ...(patch.addTagIds ?? [])], revision: (attr.revision ?? 1) + 1 }
}

const refused = (status: number, detail: string) => new ResponseError(
  new Response(JSON.stringify({ detail }), { status, headers: { 'Content-Type': 'application/json' } }))

const mounted: VueWrapper[] = []
async function open (props: Record<string, unknown>) {
  const wrapper = mount(TagsDialog as never, { props: { collectionId: 'c1', ...props } as never, global: { plugins: [Quasar] }, attachTo: document.body })
  mounted.push(wrapper)
  ;(wrapper.vm as unknown as { show: () => void }).show()
  await flushPromises()
  return wrapper
}
const transition = () => new Promise(resolve => setTimeout(resolve, 400))

const button = (wrapper: VueWrapper, label: string) => wrapper.findAllComponents(QBtn).find(b => b.props('label') === label)!
const input = (wrapper: VueWrapper, label: string) => wrapper.findAllComponents(QInput).find(i => i.props('label') === label)!
const toggle = (wrapper: VueWrapper, label: string) => wrapper.findAllComponents(QToggle).find(t => t.props('label') === label)
const switchTo = async (wrapper: VueWrapper, label: string, on: boolean) => {
  toggle(wrapper, label)!.vm.$emit('update:modelValue', on)
  await flushPromises()
}
const type = async (wrapper: VueWrapper, label: string, text: string) => {
  input(wrapper, label).vm.$emit('update:modelValue', text)
  await flushPromises()
}
const confirm = async (wrapper: VueWrapper, label: string) => {
  await button(wrapper, label).trigger('click')
  await flushPromises()
}
const text = (testid: string) => Array.from(document.querySelectorAll(`[data-testid="${testid}"]`)).map(e => e.textContent?.trim())

beforeEach(() => {
  setActivePinia(createPinia())
  listed.mockReset().mockResolvedValue([speaker, mood, topic, old])
  updated.mockReset().mockImplementation((_, id, patch) =>
    Promise.resolve(applied([speaker, mood, topic].find(a => a.id === id)!, patch)))
})
afterEach(() => {
  mounted.splice(0).forEach(w => w.unmount())
  document.body.innerHTML = ''
})

describe('TagsDialog applicable attributes', () => {
  it('offers Selected tags attributes, locks All tags ones on and leaves out retired ones', async () => {
    const wrapper = await open({ tag: person, save: vi.fn() })
    expect(listed).toHaveBeenCalledWith('c1')
    const shown = wrapper.findAllComponents(QToggle).map(t => [t.props('label'), t.props('modelValue'), t.props('disable')])
    // By name, those for all tags last.
    expect(shown).toEqual([['mood', false, false], ['speaker_type', true, false], ['topic', true, true]])
    expect(document.body.textContent).toContain('All tags')
  })

  it('creates the tag, then adds it to the switched attributes only, and closes', async () => {
    const save = vi.fn().mockResolvedValue(created)
    const wrapper = await open({ save })
    // A new tag gets only the All tags attributes on its own.
    expect(toggle(wrapper, 'speaker_type')!.props('modelValue')).toBe(false)
    await type(wrapper, 'Tag Name', 'Speaker')
    await type(wrapper, 'Tag Shorthand', 'S')
    await switchTo(wrapper, 'mood', true)
    await confirm(wrapper, 'Create')

    expect(save).toHaveBeenCalledWith(expect.objectContaining({ name: 'Speaker', shorthand: 'S' }), null)
    expect(updated.mock.calls).toEqual([['c1', 'a2', { addTagIds: ['t9'] }]])
    expect(wrapper.emitted('ok')).toEqual([[created]])
  })

  it('removes the tag from its last Selected tags attribute, leaving it for no tag', async () => {
    const save = vi.fn()
    const wrapper = await open({ tag: person, save })
    await switchTo(wrapper, 'speaker_type', false)
    await confirm(wrapper, 'Save')
    // Only this tag is taken out; the tag's own fields did not change, so they are not saved.
    expect(updated.mock.calls).toEqual([['c1', 'a1', { removeTagIds: ['t1'] }]])
    expect(save).not.toHaveBeenCalled()
    expect(wrapper.emitted('ok')).toEqual([[person]])
  })

  it('says the tag is saved only when this save wrote it', async () => {
    const save = vi.fn().mockImplementation((payload: object) => Promise.resolve({ ...person, ...payload }))
    updated.mockRejectedValue(refused(409, 'Refused.'))
    const wrapper = await open({ tag: person, save })
    await switchTo(wrapper, 'speaker_type', false)
    await confirm(wrapper, 'Save')
    expect(save).not.toHaveBeenCalled()
    expect(text('tag-dialog-error')).toEqual(['1 attribute change was not saved; Save tries again.'])

    await type(wrapper, 'Tag Name', 'Speaker')
    await confirm(wrapper, 'Save')
    expect(save).toHaveBeenCalledTimes(1)
    expect(text('tag-dialog-error')).toEqual(['The tag is saved, but 1 attribute change was not; Save tries again.'])
  })

  it('keeps a created tag when an attribute change fails, and sends only that change again', async () => {
    const message = '1 annotations with values of this attribute have a tag outside the new applicable tags; change or remove those values first.'
    const save = vi.fn().mockResolvedValue(created)
    updated.mockImplementation((_, id, patch) => id === 'a2'
      ? Promise.reject(refused(409, message))
      : Promise.resolve(applied(speaker, patch)))
    const wrapper = await open({ save })
    await type(wrapper, 'Tag Name', 'Speaker')
    await type(wrapper, 'Tag Shorthand', 'S')
    await switchTo(wrapper, 'speaker_type', true)
    await switchTo(wrapper, 'mood', true)
    await confirm(wrapper, 'Create')

    expect(wrapper.emitted('ok')).toBeUndefined()
    expect(text('tag-applicable-attribute-error')).toEqual([message])
    expect(text('tag-dialog-error')[0]).toContain('The tag is saved, but 1 attribute change was not')
    expect(document.body.textContent).toContain('Edit Tag')
    expect([toggle(wrapper, 'speaker_type')!.props('modelValue'), toggle(wrapper, 'mood')!.props('modelValue')])
      .toEqual([true, true])

    updated.mockClear()
    await confirm(wrapper, 'Save')
    expect(save).toHaveBeenCalledTimes(1)
    expect(updated.mock.calls).toEqual([['c1', 'a2', { addTagIds: ['t9'] }]])
    expect(wrapper.emitted('ok')).toBeUndefined()

    // Giving up on that change is a dismissal, not a confirmation (the reader would tag the
    // selected text on `ok`): the created tag stays, and the attributes are read again.
    listed.mockClear()
    await switchTo(wrapper, 'mood', false)
    await button(wrapper, 'Cancel').trigger('click')
    await transition()
    expect(wrapper.emitted('ok')).toBeUndefined()
    expect(wrapper.emitted('hide')).toHaveLength(1)
    expect(listed).toHaveBeenCalledWith('c1')
  })

  it('stays open with what was entered when the tag cannot be saved, and changes no attribute', async () => {
    const save = vi.fn().mockRejectedValue(refused(400, 'A tag with this name already exists'))
    const wrapper = await open({ save })
    await type(wrapper, 'Tag Name', 'Person')
    await type(wrapper, 'Tag Shorthand', 'P')
    await switchTo(wrapper, 'mood', true)
    await confirm(wrapper, 'Create')
    expect(text('tag-dialog-error')).toEqual(['A tag with this name already exists'])
    expect(updated).not.toHaveBeenCalled()
    expect([input(wrapper, 'Tag Name').props('modelValue'), toggle(wrapper, 'mood')!.props('modelValue')]).toEqual(['Person', true])
    await button(wrapper, 'Cancel').trigger('click')
    await transition()
    expect(wrapper.emitted('ok')).toBeUndefined()
  })

  it('freezes the form while saving', async () => {
    let finish!: (tag: Tag) => void
    const save = vi.fn().mockReturnValue(new Promise<Tag>(resolve => { finish = resolve }))
    const wrapper = await open({ tag: person, save })
    await type(wrapper, 'Tag Name', 'Speaker')
    await confirm(wrapper, 'Save')
    expect([input(wrapper, 'Tag Name').props('disable'), toggle(wrapper, 'mood')!.props('disable'),
      button(wrapper, 'Cancel').props('disable')]).toEqual([true, true, true])
    finish({ ...person, name: 'Speaker' })
    await flushPromises()
    expect(wrapper.emitted('ok')).toHaveLength(1)
  })

  it('still saves the tag when the attributes cannot be loaded', async () => {
    listed.mockRejectedValue(refused(503, 'Service unavailable'))
    const save = vi.fn().mockResolvedValue(created)
    const wrapper = await open({ save })
    expect(text('tag-attributes-load-error')[0]).toContain('Attributes unavailable')
    await type(wrapper, 'Tag Name', 'Speaker')
    await type(wrapper, 'Tag Shorthand', 'S')
    await confirm(wrapper, 'Create')
    expect(wrapper.emitted('ok')).toEqual([[created]])
  })
})
