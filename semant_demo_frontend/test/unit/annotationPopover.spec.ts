import { afterEach, describe, expect, it } from 'vitest'
import { DOMWrapper, mount } from '@vue/test-utils'
import { Quasar } from 'quasar'

import AnnotationPopover from 'src/features/annotations/AnnotationPopover.vue'
import type { Tag } from 'src/generated/api'

const tag = (id: string, name: string, shorthand = ''): Tag =>
  ({ id, name, shorthand, color: '#000', pictogram: '', definition: '', examples: [] })

// At least 6 tags — below that, suggestions are switched off entirely regardless of match quality.
const TAGS = [
  tag('c', 'Čapek'), tag('a', 'Aleš'), tag('n', 'Novák'), tag('b', 'Babička'),
  tag('d', 'Jirásek'), tag('e', 'Hrabal')
]

// The tag list is rendered through a `<Teleport to="body">`, so it lands in `document.body`
// rather than under the mounted wrapper's own root — queried here with a fresh DOMWrapper.
function mountPopover (selectedText = '', lastUsedTagId: string | null = null, tags: Tag[] = TAGS) {
  const wrapper = mount(AnnotationPopover, {
    props: {
      visible: true,
      tags,
      selection: {},
      selectedText,
      lastUsedTagId,
      selectedTagId: null,
      isEditing: false,
      positionChanged: false,
      editingAuto: false,
      approveRejectBusy: false,
      aiSelectionRunning: false
    },
    global: { plugins: [[Quasar, {}]] },
    attachTo: document.body
  })
  // The tag list only renders in picker mode, opened by the page via the exposed `showMode`.
  wrapper.vm.showMode('picker')
  return wrapper
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('AnnotationPopover tag list', () => {
  it('sorts tags alphabetically (case-insensitive)', async () => {
    const wrapper = mountPopover()
    await wrapper.vm.$nextTick()

    const names = new DOMWrapper(document.body).findAll('.tag-row:not(.tag-row--create) .tag-name').map((n) => n.text())
    expect(names).toEqual(['Aleš', 'Babička', 'Čapek', 'Hrabal', 'Jirásek', 'Novák'])
  })

  it('surfaces a likely-match tag first and marks it as suggested', async () => {
    const wrapper = mountPopover('Novák')
    await wrapper.vm.$nextTick()

    const rows = new DOMWrapper(document.body).findAll('.tag-row:not(.tag-row--create)')
    expect(rows[0].text()).toContain('Novák')
    expect(rows[0].classes()).toContain('is-suggested')
    // The rest stays alphabetical.
    const restNames = rows.slice(1).map((r) => r.find('.tag-name').text())
    expect(restNames).toEqual(['Aleš', 'Babička', 'Čapek', 'Hrabal', 'Jirásek'])
  })

  it('does not suggest anything when nothing resembles the selection and there is no last-used tag', async () => {
    const wrapper = mountPopover('something entirely unrelated')
    await wrapper.vm.$nextTick()

    expect(new DOMWrapper(document.body).find('.tag-row.is-suggested').exists()).toBe(false)
  })

  it('suggests the last-used tag first even for an unrelated, long selection', async () => {
    const wrapper = mountPopover('a long and entirely unrelated highlighted passage', 'b')
    await wrapper.vm.$nextTick()

    const rows = new DOMWrapper(document.body).findAll('.tag-row:not(.tag-row--create)')
    expect(rows[0].text()).toContain('Babička')
    expect(rows[0].classes()).toContain('is-suggested')
  })

  it('suggests nothing when the collection has 5 or fewer tags', async () => {
    const wrapper = mountPopover('Novák', 'b', TAGS.slice(0, 5))
    await wrapper.vm.$nextTick()

    expect(new DOMWrapper(document.body).find('.tag-row.is-suggested').exists()).toBe(false)
  })
})
