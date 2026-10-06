<template>
  <!-- Teleport targets the element itself, not a selector, as the page may mount before the layout is in the document. -->
  <Teleport v-if="sidebar.targetEl" :to="sidebar.targetEl">
    <!-- v-show keeps the state of inactive panels -->
    <div v-show="sidebar.activePanelId === id">
      <slot />
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { useRightSidebarStore } from 'src/stores/rightSidebarStore'

/**
 * Adds a panel (tool) to the right sidebar for as long as this component is mounted.
 * The slot content stays in the component tree of the page using it, so it can
 * communicate with the page through ordinary props and events.
 */
const props = withDefaults(defineProps<{
  id: string
  label: string
  icon: string
  order?: number
}>(), { order: 0 })

const sidebar = useRightSidebarStore()

onMounted(() => {
  sidebar.register({ id: props.id, label: props.label, icon: props.icon, order: props.order })
})

onBeforeUnmount(() => {
  sidebar.unregister(props.id)
})
</script>
