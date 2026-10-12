<template>
  <!-- Teleport targets the element itself, not a selector, as the page may mount before the layout is in the document. -->
  <Teleport v-if="sidebar.targetEl" :to="sidebar.targetEl">
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
import { onBeforeUnmount, onMounted, reactive, toRef } from 'vue'
import { useRightSidebarStore } from './rightSidebarStore'

/**
 * Adds a panel (tool) to the right sidebar for as long as this component is mounted.
 * The slot content stays in the component tree of the page using it, so the page passes
 * the tool its context (search results, document...) through props and handles its
 * events; the sidebar itself only knows the panel's id, label, icon and busy state.
 *
 * `fill` gives the content exactly the height of the sidebar instead of letting the
 * sidebar scroll it, for a tool that scrolls parts of itself.
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

onMounted(() => {
  // The id stays the one the panel was registered with; the rest follows the props.
  unregister = sidebar.register(reactive({
    id: props.id,
    label: toRef(props, 'label'),
    icon: toRef(props, 'icon'),
    order: toRef(props, 'order'),
    busy: toRef(props, 'busy')
  }))
})

onBeforeUnmount(() => {
  unregister?.()
  unregister = null
})
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
