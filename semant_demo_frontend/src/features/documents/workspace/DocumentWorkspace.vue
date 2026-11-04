<template>
  <div
    ref="root"
    class="document-workspace"
    :class="`document-workspace--${mode}`"
    :style="{ '--workspace-top': `${stickyTop}px`, '--workspace-height': viewHeight }"
    data-testid="document-workspace"
    :data-mode="mode"
  >
    <div v-show="mode !== 'scan'" class="document-workspace__text" data-testid="workspace-text">
      <slot />
    </div>
    <!-- Mounted also while hidden: it reads the manifest (no scans: text only) and keeps its page. -->
    <aside
      v-show="mode !== 'text'"
      class="document-workspace__scan"
      aria-label="Page scan"
      data-testid="workspace-scan"
    >
      <DocumentImagePane
        ref="pane"
        :document-id="documentId"
        :page-id="pageId"
        :document-title="documentTitle"
        :highlights="highlights"
        :layout-cache="layoutCache"
        @page-change="(page, index) => emit('pageChange', page, index)"
        @navigate="(page, index) => emit('navigate', page, index)"
        @line-select="emit('lineSelect', $event)"
        @line-focus="emit('lineFocus', $event)"
        @loaded="emit('loaded', $event)"
      />
    </aside>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import type { DocumentPage } from 'src/generated/api'
import DocumentImagePane, { type FocusRequest, type ScanHighlight, type ScanTarget } from '../scan/DocumentImagePane.vue'
import type { LayoutCache } from '../scan/pageAssets'
import type { WorkspaceMode } from './workspaceMode'

// The paired document workspace (#545): the text (the default slot: the public text or the
// collection reader) on the left and the page scan on the right. The text scrolls with its
// scroller (the page, or the document view's layout); the scan stays in view next to it
// (sticky, `stickyTop` below the scroller's top and `viewHeight` tall) and is panned and zoomed
// on its own. The owner synchronizes the two (correspondence/useTextScanSync) and chooses the
// view (`mode`, useWorkspaceMode); the workspace reports whether it is too narrow for both.

const NARROW_WIDTH = 720

withDefaults(defineProps<{
  documentId: string
  /** The view shown (useWorkspaceMode `shown`). */
  mode: WorkspaceMode
  pageId?: string | null
  documentTitle?: string
  highlights?: ScanHighlight[]
  layoutCache?: LayoutCache | null
  /** Where the scan sticks, in px below the top of the scroller (under its fixed header). */
  stickyTop?: number
  /** The height of the scroller's view, as CSS. */
  viewHeight?: string
}>(), { pageId: null, documentTitle: '', highlights: () => [], layoutCache: null, stickyTop: 0, viewHeight: '100vh' })

const emit = defineEmits<{
  'update:narrow': [narrow: boolean]
  pageChange: [page: DocumentPage, index: number]
  /** The user moved to another page in the scan viewer. */
  navigate: [page: DocumentPage, index: number]
  lineSelect: [target: ScanTarget]
  lineFocus: [target: ScanTarget]
  loaded: [info: { available: boolean, pageCount: number, pages: DocumentPage[] }]
}>()

const root = ref<HTMLElement | null>(null)
const pane = ref<InstanceType<typeof DocumentImagePane> | null>(null)

let observer: ResizeObserver | null = null
let narrow: boolean | null = null
function measure () {
  const width = root.value?.clientWidth ?? 0
  if (!width) return
  const now = width < NARROW_WIDTH
  if (now !== narrow) emit('update:narrow', (narrow = now))
}

onMounted(() => {
  measure()
  if (typeof ResizeObserver !== 'undefined' && root.value) {
    observer = new ResizeObserver(measure)
    observer.observe(root.value)
  }
})
onBeforeUnmount(() => observer?.disconnect())

/** The scan viewer's smart focus (opens the page, focuses the lines). */
const focus = async (request: FocusRequest): Promise<boolean> => (await pane.value?.focus(request)) ?? false
const currentPage = () => pane.value?.currentPage ?? null

defineExpose({ focus, currentPage })

</script>

<style scoped>
.document-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.document-workspace--text,
.document-workspace--scan {
  grid-template-columns: minmax(0, 1fr);
}

.document-workspace__text {
  min-width: 0;
}

.document-workspace__scan {
  position: sticky;
  top: var(--workspace-top, 0px);
  height: calc(var(--workspace-height, 100vh) - var(--workspace-top, 0px) - 8px);
  min-height: 320px;
  border: 1px solid #d5dce6;
  border-radius: 12px;
  overflow: hidden;
  background: #fff;
}
</style>
