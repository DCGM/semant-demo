import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'

export interface RightSidebarPanelInfo {
  id: string
  label: string
  icon: string
  order: number
}

interface RegisteredPanel extends RightSidebarPanelInfo {
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
  const open = ref(false)
  const miniState = ref(false)
  // element the panels teleport their content into; set by the shell once mounted
  const targetEl = shallowRef<HTMLElement | null>(null)

  const sortedPanels = computed<RightSidebarPanelInfo[]>(() =>
    [...panels.value]
      .sort((a, b) => a.order - b.order)
      .map(({ id, label, icon, order }) => ({ id, label, icon, order }))
  )
  const hasPanels = computed(() => panels.value.length > 0)
  const activePanel = computed(() => sortedPanels.value.find(p => p.id === activePanelId.value) ?? null)

  /**
   * Adds a panel; returns the function that removes it again. A second panel with an id
   * that is already shown is refused (with a warning), and its unregister does nothing,
   * so it cannot remove the first one.
   */
  function register (panel: RightSidebarPanelInfo): () => void {
    if (panels.value.some(p => p.id === panel.id)) {
      console.warn(`Right sidebar panel "${panel.id}" is already registered.`)
      return () => undefined
    }
    const owner = Symbol(panel.id)
    panels.value.push({ ...panel, owner })
    if (activePanelId.value === null) {
      activePanelId.value = sortedPanels.value[0].id
    }
    return () => unregister(owner)
  }

  function unregister (owner: symbol) {
    const removed = panels.value.find(p => p.owner === owner)
    if (!removed) return
    panels.value = panels.value.filter(p => p.owner !== owner)
    if (activePanelId.value === removed.id) {
      activePanelId.value = sortedPanels.value[0]?.id ?? null
    }
    if (!hasPanels.value) {
      // the state is not remembered between pages
      miniState.value = false
    }
  }

  // brings the panel to front and makes sure it is visible
  function activate (id: string) {
    if (!panels.value.some(p => p.id === id)) return
    activePanelId.value = id
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
    activate,
    toggleOpen,
    toggleMiniState
  }
})
