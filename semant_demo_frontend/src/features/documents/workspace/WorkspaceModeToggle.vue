<template>
  <!-- Shown only for a document with scans; on a narrow screen only one of the two fits. -->
  <q-btn-toggle
    :model-value="value"
    :options="options"
    dense no-caps unelevated
    toggle-color="primary"
    color="white"
    text-color="grey-8"
    class="workspace-mode-toggle"
    aria-label="Document view"
    data-testid="workspace-mode"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { WorkspaceMode } from './workspaceMode'

const props = defineProps<{
  /** The view shown (workspaceMode.ts `shownMode`). */
  modelValue: WorkspaceMode
  narrow: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [mode: WorkspaceMode] }>()

const value = computed(() => props.modelValue)
// In the order of the panes: the scan on the left, the text on the right.
const options = computed(() => [
  { value: 'scan', label: 'Scan', icon: 'image' },
  ...(props.narrow ? [] : [{ value: 'split', label: 'Text and scan', icon: 'vertical_split' }]),
  { value: 'text', label: 'Text', icon: 'article' }
])
</script>

<style scoped>
.workspace-mode-toggle {
  border: 1px solid rgba(15, 23, 42, 0.16);
}
</style>
