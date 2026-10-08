import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { Quasar } from 'quasar'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h, nextTick, ref } from 'vue'

import { useRightSidebarStore } from 'src/app/sidebar/rightSidebarStore'
import RightSidebarPanel from 'src/app/sidebar/RightSidebarPanel.vue'

const panel = (id: string, order = 0) => ({ id, label: `Label ${id}`, icon: 'star', order })

describe('rightSidebarStore', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('shows the first registered panel and falls back when it goes', () => {
    const sidebar = useRightSidebarStore()
    expect(sidebar.hasPanels).toBe(false)

    const removeSummary = sidebar.register(panel('summary', 1))
    const removeNotes = sidebar.register(panel('notes', 0))
    expect(sidebar.sortedPanels.map((p) => p.id)).toEqual(['notes', 'summary'])
    expect(sidebar.activePanelId).toBe('summary') // the first one stays active

    removeSummary()
    expect(sidebar.activePanelId).toBe('notes')
    removeNotes()
    expect([sidebar.hasPanels, sidebar.activePanelId]).toEqual([false, null])
  })

  it('refuses a duplicate id without letting the duplicate remove the original', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const sidebar = useRightSidebarStore()
    sidebar.register(panel('summary'))
    const removeDuplicate = sidebar.register(panel('summary'))
    expect(sidebar.sortedPanels.map((p) => p.id)).toEqual(['summary'])

    removeDuplicate()

    expect(sidebar.sortedPanels.map((p) => p.id)).toEqual(['summary'])
  })

  it('activate opens the sidebar on a registered panel only', () => {
    const sidebar = useRightSidebarStore()
    sidebar.register(panel('a'))
    sidebar.register(panel('b'))
    sidebar.miniState = true

    sidebar.activate('b')
    expect([sidebar.activePanelId, sidebar.open, sidebar.miniState]).toEqual(['b', true, false])
    sidebar.activate('missing')
    expect(sidebar.activePanelId).toBe('b')
  })

  it('forgets the mini state when the last panel goes', () => {
    const sidebar = useRightSidebarStore()
    const remove = sidebar.register(panel('a'))
    sidebar.toggleMiniState()
    remove()
    expect(sidebar.miniState).toBe(false)
  })
})

describe('RightSidebarPanel', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  // Two "pages" with their own panels and their own context (a prop they pass to the tool).
  const Tool = defineComponent({
    props: { context: { type: String, required: true } },
    emits: ['act'],
    setup: (props, { emit }) => () => h('button', { onClick: () => emit('act', props.context) }, `tool for ${props.context}`)
  })

  function mountShell () {
    const target = document.createElement('div')
    document.body.appendChild(target)
    useRightSidebarStore().targetEl = target
    return target
  }

  it('renders the page\'s tool in the sidebar with the context the page passes', async () => {
    const target = mountShell()
    const acted: string[] = []
    const context = ref('search 1')
    const Page = defineComponent({
      setup: () => () => h(RightSidebarPanel, { id: 'summary', label: 'Summary', icon: 'star' }, {
        default: () => h(Tool, { context: context.value, onAct: (c: string) => acted.push(c) })
      })
    })
    const wrapper = mount(Page, { global: { plugins: [[Quasar, {}]] } })
    await nextTick()

    expect(useRightSidebarStore().sortedPanels.map((p) => p.id)).toEqual(['summary'])
    expect(target.textContent).toBe('tool for search 1')

    context.value = 'search 2'
    await nextTick()
    expect(target.textContent).toBe('tool for search 2')
    target.querySelector('button')!.click()
    expect(acted).toEqual(['search 2']) // the tool talks to its page, not to the sidebar

    wrapper.unmount()
    expect(useRightSidebarStore().hasPanels).toBe(false)
    expect(target.textContent).toBe('')
  })

  it('switches panels when the user moves to another page', async () => {
    const target = mountShell()
    const page = (id: string) => defineComponent({
      setup: () => () => h(RightSidebarPanel, { id, label: id, icon: 'star' }, {
        default: () => h(Tool, { context: id })
      })
    })
    const currentPage = ref<'search' | 'document'>('search')
    const SearchPage = page('search-summary')
    const DocumentPage = page('document-notes')
    const App = defineComponent({
      setup: () => () => h(currentPage.value === 'search' ? SearchPage : DocumentPage)
    })
    mount(App, { global: { plugins: [[Quasar, {}]] } })
    await nextTick()
    const sidebar = useRightSidebarStore()
    expect([sidebar.activePanelId, target.textContent]).toEqual(['search-summary', 'tool for search-summary'])

    currentPage.value = 'document'
    await nextTick()
    await nextTick()

    expect(sidebar.sortedPanels.map((p) => p.id)).toEqual(['document-notes'])
    expect([sidebar.activePanelId, target.textContent]).toEqual(['document-notes', 'tool for document-notes'])
  })

  it('keeps an inactive panel mounted but hidden', async () => {
    const target = mountShell()
    const Page = defineComponent({
      setup: () => () => [
        h(RightSidebarPanel, { id: 'a', label: 'A', icon: 'star' }, { default: () => h(Tool, { context: 'a' }) }),
        h(RightSidebarPanel, { id: 'b', label: 'B', icon: 'star' }, { default: () => h(Tool, { context: 'b' }) })
      ]
    })
    mount(Page, { global: { plugins: [[Quasar, {}]] } })
    await nextTick()
    useRightSidebarStore().activate('b')
    await nextTick()

    const panels = Array.from(target.querySelectorAll<HTMLElement>('[data-sidebar-panel]'))
    expect(panels.map((p) => [p.dataset.sidebarPanel, p.style.display])).toEqual([['a', 'none'], ['b', '']])
  })
})
