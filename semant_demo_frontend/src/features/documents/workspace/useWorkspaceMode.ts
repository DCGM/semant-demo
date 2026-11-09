import { computed, ref } from 'vue'
import { shownMode, type WorkspaceMode } from './workspaceMode'

/**
 * The chosen and the shown view of a document workspace. `hasScan` comes from the scan
 * viewer's manifest (`DocumentWorkspace` `loaded`), `narrow` from the workspace's width
 * (`v-model:narrow`); the chosen view is kept while they change.
 */
export function useWorkspaceMode (initial: WorkspaceMode | null = null) {
  const chosen = ref<WorkspaceMode>(initial ?? 'split')
  const hasScan = ref(false)
  const narrow = ref(false)
  const shown = computed(() => shownMode(chosen.value, { hasScan: hasScan.value, narrow: narrow.value }))
  return { chosen, hasScan, narrow, shown }
}

export type WorkspaceModeState = ReturnType<typeof useWorkspaceMode>
