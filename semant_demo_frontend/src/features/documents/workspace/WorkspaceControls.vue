<template>
  <!-- The controls row of the document views (#600), fixed above the panes: the owner's
       reader tools (default slot), the synchronization notice and the view toggle. A notice
       takes the room left in the row, so it never moves the text or resizes the scan. -->
  <div class="workspace-controls" role="toolbar" aria-label="Document view controls" data-testid="workspace-controls">
    <slot />
    <div class="workspace-controls__notice text-caption ellipsis" :title="notice">
      <span v-if="notice" aria-live="polite" data-testid="sync-notice">{{ notice }}</span>
    </div>
    <WorkspaceModeToggle
      v-if="hasScan"
      :model-value="mode"
      :narrow="narrow"
      @update:model-value="emit('update:mode', $event)"
    />
  </div>
</template>

<script setup lang="ts">
import type { WorkspaceMode } from './workspaceMode'
import WorkspaceModeToggle from './WorkspaceModeToggle.vue'

withDefaults(defineProps<{
  /** The view shown (useWorkspaceMode `shown`). */
  mode: WorkspaceMode
  narrow: boolean
  /** The document has scans: the view can be chosen. */
  hasScan: boolean
  notice?: string
}>(), { notice: '' })

const emit = defineEmits<{ 'update:mode': [mode: WorkspaceMode] }>()
</script>

<style scoped>
.workspace-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  flex: none;
  min-height: 40px;
  padding: 3px 12px;
  background: #fff;
  border-bottom: 1px solid #e2e8f0;
}

.workspace-controls__notice {
  flex: 1 1 0;
  min-width: 0;
  color: #475569;
}
</style>
