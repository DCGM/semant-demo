import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'

export interface RightSidebarPanelInfo {
  id: string
  label: string
  icon: string
  order: number
  // work of the panel is under way (shown on its rail icon)
  busy?: boolean
}

interface RegisteredPanel {
  // kept by reference: a reactive object passed by the panel updates its label, icon,
  // order and busy state
  panel: RightSidebarPanelInfo
  owner: symbol
}

/**
 * App-shell state of the right sidebar (RightSidebar.vue): which panels are registered,
 * which one is shown, open/mini state and the element panels are rendered into. Pages
 * contribute panels through RightSidebarPanel.vue. Feature/business state (search
 * results, summaries, documents...) does not belong here: panels get it from their page
 * through props.
 */
export const useRightSidebarStore = defineStore('rightSidebar', () => {
  const panels = ref<RegisteredPanel[]>([])
  const activePanelId = ref<string | null>(null)
  // Until a panel is chosen (`select`/`activate`: the user, the page or a kept-alive page
  // restoring its panel), the active panel is the default one: the lowest `order` among the
  // registered panels, whatever order they registered in (Vue mounts panels in its own order).
  let activeIsDefault = true
  const open = ref(false)
  const miniState = ref(false)
  // element the panels teleport their content into; set by the shell once mounted
  const targetEl = shallowRef<HTMLElement | null>(null)

  const sortedPanels = computed<RightSidebarPanelInfo[]>(() =>
    panels.value
      .map(({ panel: { id, label, icon, order, busy } }) => ({ id, label, icon, order, busy: busy ?? false }))
      .sort((a, b) => a.order - b.order)
  )
  const hasPanels = computed(() => panels.value.length > 0)
  const activePanel = computed(() => sortedPanels.value.find(p => p.id === activePanelId.value) ?? null)

  /**
   * Adds a panel; returns the function that removes it again. A second panel with an id
   * that is already shown is refused (with a warning), and its unregister does nothing,
   * so it cannot remove the first one.
   */
  function register (panel: RightSidebarPanelInfo): () => void {
    if (panels.value.some(p => p.panel.id === panel.id)) {
      console.warn(`Right sidebar panel "${panel.id}" is already registered.`)
      return () => undefined
    }
    const owner = Symbol(panel.id)
    panels.value.push({ panel, owner })
    if (activePanelId.value === null || activeIsDefault) {
      activePanelId.value = sortedPanels.value[0].id
      activeIsDefault = true
    }
    return () => unregister(owner)
  }

  function unregister (owner: symbol) {
    const removed = panels.value.find(p => p.owner === owner)
    if (!removed) return
    panels.value = panels.value.filter(p => p.owner !== owner)
    if (activePanelId.value === removed.panel.id) {
      activePanelId.value = sortedPanels.value[0]?.id ?? null
      activeIsDefault = true
    }
    if (!hasPanels.value) {
      // the state is not remembered between pages
      miniState.value = false
    }
  }

  // shows the panel without opening the sidebar; a panel registered later no longer replaces it
  function select (id: string) {
    if (!panels.value.some(p => p.panel.id === id)) return
    activePanelId.value = id
    activeIsDefault = false
  }

  // brings the panel to front and makes sure it is visible
  function activate (id: string) {
    if (!panels.value.some(p => p.panel.id === id)) return
    select(id)
    open.value = true
    miniState.value = false
  }

  function toggleOpen () {
    open.value = !open.value
  }

  function toggleMiniState () {
    miniState.value = !miniState.value
  }

  return {
    sortedPanels,
    hasPanels,
    activePanelId,
    activePanel,
    open,
    miniState,
    targetEl,
    register,
    select,
    activate,
    toggleOpen,
    toggleMiniState
  }
})
