<template>
  <!-- Teleport targets the element itself, not a selector, as the page may mount before the layout is in the document. -->
  <Teleport v-if="sidebar.targetEl" :to="sidebar.targetEl">
    <!-- v-show keeps the state of inactive panels -->
    <div v-show="sidebar.activePanelId === id" :data-sidebar-panel="id">
      <slot />
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { useRightSidebarStore } from './rightSidebarStore'

/**
 * Adds a panel (tool) to the right sidebar for as long as this component is mounted.
 * The slot content stays in the component tree of the page using it, so the page passes
 * the tool its context (search results, document...) through props and handles its
 * events; the sidebar itself only knows the panel's id, label and icon.
 */
const props = withDefaults(defineProps<{
  id: string
  label: string
  icon: string
  order?: number
}>(), { order: 0 })

const sidebar = useRightSidebarStore()
let unregister: (() => void) | null = null

onMounted(() => {
  unregister = sidebar.register({ id: props.id, label: props.label, icon: props.icon, order: props.order })
})

onBeforeUnmount(() => {
  unregister?.()
  unregister = null
})
</script>
