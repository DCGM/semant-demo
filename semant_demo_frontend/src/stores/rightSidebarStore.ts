import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'

export interface RightSidebarPanelInfo {
  id: string
  label: string
  icon: string
  order: number
}

/**
 * State of the right sidebar shell (RightSidebar.vue).
 * Pages contribute content through RightSidebarPanel.vue, which registers here.
 */
export const useRightSidebarStore = defineStore('rightSidebar', () => {
  const panels = ref<RightSidebarPanelInfo[]>([])
  const activePanelId = ref<string | null>(null)
  const open = ref(false)
  const miniState = ref(false)
  // element the panels teleport their content into; set by the shell once mounted
  const targetEl = shallowRef<HTMLElement | null>(null)

  const sortedPanels = computed(() => [...panels.value].sort((a, b) => a.order - b.order))
  const hasPanels = computed(() => panels.value.length > 0)
  const activePanel = computed(() => panels.value.find(p => p.id === activePanelId.value) ?? null)

  function register (panel: RightSidebarPanelInfo) {
    if (panels.value.some(p => p.id === panel.id)) {
      console.warn(`Right sidebar panel "${panel.id}" is already registered.`)
      return
    }
    panels.value.push(panel)
    if (activePanelId.value === null) {
      activePanelId.value = sortedPanels.value[0].id
    }
  }

  function unregister (id: string) {
    panels.value = panels.value.filter(p => p.id !== id)
    if (activePanelId.value === id) {
      activePanelId.value = sortedPanels.value[0]?.id ?? null
    }
    if (!hasPanels.value) {
      // the state is not remembered between pages
      miniState.value = false
    }
  }

  // brings the panel to front and makes sure it is visible
  function activate (id: string) {
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
    panels,
    sortedPanels,
    hasPanels,
    activePanelId,
    activePanel,
    open,
    miniState,
    targetEl,
    register,
    unregister,
    activate,
    toggleOpen,
    toggleMiniState
  }
})
