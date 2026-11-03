<template>
  <!-- Teleport targets the element itself, not a selector, as the page may mount before the layout is in the document. -->
  <Teleport v-if="sidebar.targetEl && shown" :to="sidebar.targetEl">
    <!-- v-show keeps the state of inactive panels -->
    <div
      v-show="sidebar.activePanelId === id"
      class="sidebar-panel"
      :class="{ 'sidebar-panel--fill': fill }"
      :data-sidebar-panel="id"
    >
      <slot />
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { onActivated, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, toRef } from 'vue'
import { useRightSidebarStore } from './rightSidebarStore'

/**
 * Adds a panel (tool) to the right sidebar for as long as this component is mounted.
 * The slot content stays in the component tree of the page using it, so the page passes
 * the tool its context (search results, document...) through props and handles its
 * events; the sidebar itself only knows the panel's id, label, icon and busy state.
 *
 * `fill` gives the content exactly the height of the sidebar instead of letting the
 * sidebar scroll it, for a tool that scrolls parts of itself.
 *
 * On a page kept alive while another one is shown (MainLayout, #545), the panel is removed
 * while the page is hidden and added again, as the active one if it was, when it returns.
 * Its content is rendered anew then: a tool's state belongs to its page's composables.
 */
const props = withDefaults(defineProps<{
  id: string
  label: string
  icon: string
  order?: number
  busy?: boolean
  fill?: boolean
}>(), { order: 0, busy: false, fill: false })

const sidebar = useRightSidebarStore()
let unregister: (() => void) | null = null
/** False while the page is kept alive but hidden. */
const shown = ref(true)
let wasActive = false

function add () {
  if (unregister) return
  // The id stays the one the panel was registered with; the rest follows the props.
  unregister = sidebar.register(reactive({
    id: props.id,
    label: toRef(props, 'label'),
    icon: toRef(props, 'icon'),
    order: toRef(props, 'order'),
    busy: toRef(props, 'busy')
  }))
}

function remove () {
  unregister?.()
  unregister = null
}

onMounted(add)

onActivated(() => {
  add()
  shown.value = true
  if (wasActive) sidebar.activePanelId = props.id
})

onDeactivated(() => {
  wasActive = sidebar.activePanelId === props.id
  shown.value = false
  // Removed once every panel of the page has noted whether it was the active one: removing
  // the active panel makes another one active.
  void Promise.resolve().then(() => { if (!shown.value) remove() })
})

onBeforeUnmount(remove)
</script>

<style scoped>
.sidebar-panel {
  flex: none;
}

.sidebar-panel--fill {
  flex: 1 1 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.sidebar-panel--fill > :deep(*) {
  flex: 1 1 0;
  min-height: 0;
}
</style>
