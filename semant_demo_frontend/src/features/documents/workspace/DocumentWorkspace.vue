<template>
  <div
    ref="root"
    class="document-workspace"
    :class="[`document-workspace--${mode}`, { 'document-workspace--resizing': dragging }]"
    :style="splitStyle"
    data-testid="document-workspace"
    :data-mode="mode"
  >
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
    <div
      v-if="mode === 'split'"
      class="document-workspace__divider"
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the text and the scan"
      :aria-controls="textId"
      :aria-valuenow="Math.round(shownShare * 100)"
      :aria-valuemin="Math.round(bounds.min * 100)"
      :aria-valuemax="Math.round(bounds.max * 100)"
      tabindex="0"
      title="Drag, or use the arrow keys, to resize the text and the scan; double-click to reset"
      data-testid="workspace-divider"
      @pointerdown.prevent="onDividerDown"
      @pointermove="onDividerMove"
      @pointerup="onDividerUp"
      @pointercancel="onDividerUp"
      @dblclick="setShare(DEFAULT_TEXT_SHARE)"
      @keydown="onDividerKey"
    ></div>
    <!-- The text's own scroller: the views around it do not scroll (#600). -->
    <div
      v-show="mode !== 'scan'"
      :id="textId"
      class="document-workspace__text"
      data-testid="workspace-text"
    >
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { DocumentPage } from 'src/generated/api'
import DocumentImagePane, { type FocusRequest, type ScanHighlight, type ScanTarget } from '../scan/DocumentImagePane.vue'
import type { LayoutCache } from '../scan/pageAssets'
import {
  DEFAULT_TEXT_SHARE, DIVIDER_WIDTH, KEY_STEP, LARGE_KEY_STEP, MIN_SCAN_WIDTH, MIN_TEXT_WIDTH,
  clampShare, readShare, shareAt, shareBounds, storeShare
} from './splitRatio'
import type { WorkspaceMode } from './workspaceMode'

// The paired document workspace (#545): the page scan on the left and the text (the default
// slot: the public text or the collection reader) on the right (#600). It fills the height its owner
// gives it (#600): the text scrolls in its own scroller, the scan is panned and zoomed on its
// own with its page controls and thumbnails in view. The divider between them is dragged or
// moved with the arrow keys; the split is remembered in this browser (splitRatio.ts). The owner
// synchronizes the two (correspondence/useTextScanSync) and chooses the view (`mode`,
// useWorkspaceMode); the workspace reports whether it is too narrow for both.

const NARROW_WIDTH = 720

withDefaults(defineProps<{
  documentId: string
  /** The view shown (useWorkspaceMode `shown`). */
  mode: WorkspaceMode
  pageId?: string | null
  documentTitle?: string
  highlights?: ScanHighlight[]
  layoutCache?: LayoutCache | null
}>(), { pageId: null, documentTitle: '', highlights: () => [], layoutCache: null })

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
const textId = `document-workspace-text-${Math.random().toString(36).slice(2, 10)}`

/** The text's share of the width (as chosen; the panes' minimum widths may narrow it). */
const share = ref(readShare())
const width = ref(0)
const bounds = computed(() => shareBounds(width.value))
const shownShare = computed(() => clampShare(share.value, width.value))
const dragging = ref(false)
const splitStyle = computed(() => ({
  '--text-share': String(share.value),
  '--divider-width': `${DIVIDER_WIDTH}px`,
  '--min-text-width': `${MIN_TEXT_WIDTH}px`,
  '--min-scan-width': `${MIN_SCAN_WIDTH}px`
}))

function setShare (value: number) {
  share.value = clampShare(value, width.value)
  storeShare(share.value)
}

function onDividerDown (e: PointerEvent) {
  if (e.button !== 0 || !root.value) return
  dragging.value = true
  ;(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId)
  ;(e.currentTarget as HTMLElement).focus({ preventScroll: true })
}

function onDividerMove (e: PointerEvent) {
  if (!dragging.value || !root.value) return
  const box = root.value.getBoundingClientRect()
  share.value = shareAt(e.clientX - box.left, box.width)
}

function onDividerUp (e: PointerEvent) {
  if (!dragging.value) return
  dragging.value = false
  ;(e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId)
  storeShare(share.value)
}

function onDividerKey (e: KeyboardEvent) {
  const step = e.shiftKey ? LARGE_KEY_STEP : KEY_STEP
  const now = shownShare.value
  const next = ({
    // The divider moves with the arrow; the text is on its right.
    ArrowLeft: now + step,
    ArrowRight: now - step,
    Home: bounds.value.min,
    End: bounds.value.max
  } as Record<string, number>)[e.key]
  if (next === undefined) return
  e.preventDefault()
  setShare(next)
}

let observer: ResizeObserver | null = null
let narrow: boolean | null = null
function measure () {
  const now = root.value?.clientWidth ?? 0
  if (!now) return
  width.value = now
  const isNarrow = now < NARROW_WIDTH
  if (isNarrow !== narrow) emit('update:narrow', (narrow = isNarrow))
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
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}

.document-workspace--resizing {
  cursor: col-resize;
  user-select: none;
}

/* The text pane: the reading surface and its scroller. */
.document-workspace__text {
  flex: 1 1 0;
  min-width: 0;
  overflow-x: hidden;
  overflow-y: auto;
  background: #fff;
}

/* Side by side: the text gets its share, both panes keep a usable width (splitRatio.ts). */
.document-workspace--split .document-workspace__text {
  flex: 0 1 calc((100% - var(--divider-width)) * var(--text-share));
  min-width: var(--min-text-width);
}

.document-workspace__scan {
  flex: 1 1 0;
  min-width: 0;
  overflow: hidden;
  background: #fff;
}

.document-workspace--split .document-workspace__scan {
  min-width: var(--min-scan-width);
}

/* A thin line between the panes in an 8px wide grip. */
.document-workspace__divider {
  position: relative;
  flex: none;
  width: var(--divider-width);
  cursor: col-resize;
  touch-action: none;
  background: #f1f5f9;
  border-left: 1px solid #e2e8f0;
  border-right: 1px solid #e2e8f0;
  transition: background 0.15s;
}

.document-workspace__divider::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 1px;
  width: 4px;
  height: 32px;
  margin-top: -16px;
  border-radius: 2px;
  background: #cbd5e1;
}

.document-workspace__divider:hover,
.document-workspace--resizing .document-workspace__divider {
  background: #e2e8f0;
}

.document-workspace__divider:focus-visible {
  outline: 2px solid var(--q-primary);
  outline-offset: -2px;
}

/* Over the panes while dragging, so neither the text nor the scan takes the pointer. */
.document-workspace--resizing .document-workspace__text,
.document-workspace--resizing .document-workspace__scan {
  pointer-events: none;
}
</style>
