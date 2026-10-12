import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { Quasar } from 'quasar'
import { createPinia, setActivePinia } from 'pinia'

import AiAssistPanel from 'src/features/annotations/AiAssistPanel.vue'
import DocumentTagsPanel from 'src/features/annotations/DocumentTagsPanel.vue'
import { useTagsStore } from 'src/features/annotations/tagsStore'

const tag = (id: string, name: string) => ({ id, name, color: '#000', shorthand: id, collectionId: 'c1' })

vi.mock('src/features/annotations/useTagsRepository', () => ({
  useTagsRepository: () => ({ getAllByCollection: async () => [tag('t1', 'Person'), tag('t2', 'Place')] })
}))
vi.mock('src/features/annotations/useTagSpansRepository', () => ({ useTagSpansRepository: () => ({}) }))
vi.mock('src/shared/api', async () => ({
  ...(await vi.importActual<typeof import('src/shared/api')>('src/shared/api')),
  useApi: () => ({ default: {} })
}))

// The drawer keeps both panels alive across tab switches (keep-alive), so they reset
// their own collection-specific state when the collection changes.
describe('document view panels on a context change', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    await useTagsStore().fetchTagsByCollection('c1')
  })

  const mountPanel = (component: typeof AiAssistPanel | typeof DocumentTagsPanel) =>
    mount(component, {
      props: { collectionId: 'c1', documentId: 'd1' },
      global: { plugins: [[Quasar, {}]] }
    })

  it('AI assist keeps the chosen tags for another document and drops them for another collection', async () => {
    const wrapper = mountPanel(AiAssistPanel)
    const checkbox = () => wrapper.find('.ai-tag-checkbox')
    await checkbox().trigger('click')
    expect(checkbox().attributes('aria-checked')).toBe('true')

    await wrapper.setProps({ documentId: 'd2' })
    expect(checkbox().attributes('aria-checked')).toBe('true')

    await wrapper.setProps({ collectionId: 'c2' })
    expect(checkbox().attributes('aria-checked')).toBe('false')
  })

  it('the tags panel keeps its search for another document and clears it for another collection', async () => {
    const wrapper = mountPanel(DocumentTagsPanel)
    await wrapper.find('input').setValue('Pla')
    expect(wrapper.findAll('.tag-card')).toHaveLength(1)

    await wrapper.setProps({ documentId: 'd2' })
    expect(wrapper.findAll('.tag-card')).toHaveLength(1)

    await wrapper.setProps({ collectionId: 'c2' })
    expect(wrapper.findAll('.tag-card')).toHaveLength(2)
  })
})
