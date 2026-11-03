<template>
  <section
    class="image-pane"
    :aria-label="`Page scans of ${documentTitle || 'the document'}`"
    data-testid="document-image-pane"
    @keydown="onKeydown"
  >
    <div v-if="manifestState === 'loading'" class="image-pane__message">
      <q-spinner size="28px" color="primary" class="q-mr-sm" /> Loading the pages…
    </div>
    <div v-else-if="manifestState === 'error'" class="image-pane__message text-negative" role="alert">
      <q-icon name="error_outline" size="22px" class="q-mr-sm" />
      {{ manifestError }}
      <q-btn flat dense no-caps color="primary" label="Retry" class="q-ml-sm" @click="loadManifest" />
    </div>
    <div v-else-if="!pages.length" class="image-pane__message text-grey-8" data-testid="image-pane-text-only">
      <q-icon name="hide_image" size="22px" class="q-mr-sm" />
      This document has no page scans; it can be read as text only.
    </div>

    <template v-else>
      <div class="image-pane__toolbar" role="toolbar" aria-label="Page scan controls">
        <q-btn
          flat dense round icon="chevron_left" aria-label="Previous page"
          :disable="currentIndex <= 0" @click="goToPage(currentIndex - 1)"
        />
        <form class="image-pane__jump" @submit.prevent="jump">
          <q-input
            v-model="jumpText"
            dense outlined
            class="image-pane__jump-input"
            input-class="text-center"
            :placeholder="currentLabel"
            aria-label="Go to page (printed label or position)"
            :error="jumpError !== null"
            :error-message="jumpError ?? undefined"
            hide-bottom-space
            data-testid="page-jump"
            @update:model-value="jumpError = null"
          />
        </form>
        <span class="image-pane__position text-grey-8" data-testid="page-position">
          {{ currentIndex + 1 }} / {{ pages.length }}
        </span>
        <q-btn
          flat dense round icon="chevron_right" aria-label="Next page"
          :disable="currentIndex >= pages.length - 1" @click="goToPage(currentIndex + 1)"
        />
        <q-space />
        <span v-if="layoutNotice" class="image-pane__notice text-grey-8" data-testid="layout-notice">
          {{ layoutNotice }}
          <q-btn
            v-if="layoutState === 'error'" flat dense no-caps size="sm" color="primary" label="Retry"
            @click="layoutLoad = loadLayout(currentPage!)"
          />
        </span>
        <q-btn flat dense round icon="zoom_out" aria-label="Zoom out (−)" :disable="!canZoom" @click="view?.zoomOut()" />
        <span class="image-pane__zoom text-grey-8" aria-live="off" data-testid="zoom-level">{{ zoomPercent }}%</span>
        <q-btn flat dense round icon="zoom_in" aria-label="Zoom in (+)" :disable="!canZoom" @click="view?.zoomIn()" />
        <q-btn flat dense round icon="fit_screen" aria-label="Fit the page (0)" :disable="!canZoom" @click="view?.fit()" />
      </div>

      <div
        ref="viewport"
        class="image-pane__viewport"
        tabindex="0"
        role="group"
        aria-roledescription="page scan"
        :aria-label="currentPage ? pageName(currentPage, currentIndex) : 'Page'"
        aria-describedby="image-pane-keys"
        data-testid="scan-viewport"
        @pointerdown="viewport?.focus({ preventScroll: true })"
      >
        <ScanPageView
          v-if="currentPage?.imageUrl"
          ref="view"
          :page-key="currentPage.pageId"
          :src="assetUrl(currentPage.imageUrl)"
          :size="pageSize(currentPage)"
          :layout="layout"
          :active-line-id="activeLineId"
          :highlights="pageHighlights"
          :image-alt="`Scan of ${pageName(currentPage, currentIndex).toLowerCase()}`"
          @line-click="onLineClick"
          @zoom="zoomPercent = $event"
          @image-state="imageState = $event"
        />
        <div v-else class="image-pane__message text-grey-8" data-testid="no-scan">
          <q-icon name="hide_image" size="22px" class="q-mr-sm" />
          No scan of this page is available.
        </div>
      </div>
      <span id="image-pane-keys" class="sr-only">
        Up and Down arrows: previous or next text line. Page Up and Page Down: previous or next page.
        Plus and minus: zoom. Zero: fit the page.
      </span>
      <span class="sr-only" aria-live="polite" data-testid="line-announcement">{{ announcement }}</span>

      <PageThumbnailStrip
        v-if="showThumbnails"
        :pages="pages"
        :current-index="currentIndex"
        @select="goToPage"
      />
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { DocumentPage } from 'src/generated/api'
import { apiErrorMessage, isAbortError } from 'src/shared/api'
import ScanPageView, { type LineHighlight } from './ScanPageView.vue'
import PageThumbnailStrip from './PageThumbnailStrip.vue'
import { assetUrl, createLayoutCache, readDocumentPages, type LayoutCache } from './pageAssets'
import { adjacentLine, findPage, pageName } from './pageNavigation'
import type { PageLayout } from './pageLayout'

// The scan half of the document workspace (#543, parent #351): one whole page at a time
// with its OCR line overlay, page navigation and a thumbnail strip. It reads the page
// manifest and layout files (#541) itself, lazily and for the current page only, and
// knows nothing of the text: it reports line clicks and keyboard focus as
// `{ pageId, lineId, offset? }` and takes highlights and focus requests in the same terms.
// The text/scan correspondence is a separate module (#544).

export interface ScanTarget {
  pageId: string
  lineId: string
  /** Approximate UTF-16 offset in the line's text (word start); absent for a whole line. */
  offset?: number
}

export interface ScanHighlight extends LineHighlight {
  pageId: string
}

export interface FocusRequest {
  pageId: string
  /** The lines to bring into view (the first is focused); none: just open the page. */
  lineIds?: string[]
  /** Part of the first line, UTF-16 offsets in its text. */
  start?: number
  end?: number
}

const props = withDefaults(defineProps<{
  documentId: string
  /** The page shown (v-model:pageId); the first page when null or unknown. */
  pageId?: string | null
  highlights?: ScanHighlight[]
  showThumbnails?: boolean
  documentTitle?: string
  /** For tests: a layout cache of another loader. */
  layoutCache?: LayoutCache | null
}>(), { pageId: null, highlights: () => [], showThumbnails: true, documentTitle: '', layoutCache: null })

const emit = defineEmits<{
  'update:pageId': [pageId: string]
  /** The shown page changed (also the first page after loading). */
  pageChange: [page: DocumentPage, index: number]
  /** A line was clicked. */
  lineSelect: [target: ScanTarget]
  /** A line became the current one by keyboard (Up/Down). */
  lineFocus: [target: ScanTarget]
  /** The manifest was read; `available` false: a text-only document. */
  loaded: [info: { available: boolean, pageCount: number }]
}>()

const pages = ref<DocumentPage[]>([])
const manifestState = ref<'loading' | 'loaded' | 'error'>('loading')
const manifestError = ref('')
const currentIndex = ref(0)
const layout = ref<PageLayout | null>(null)
const layoutState = ref<'none' | 'loading' | 'loaded' | 'error'>('none')
const imageState = ref<'loading' | 'loaded' | 'error'>('loading')
const activeLineId = ref<string | null>(null)
const announcement = ref('')
const zoomPercent = ref(100)
const jumpText = ref('')
const jumpError = ref<string | null>(null)
const view = ref<InstanceType<typeof ScanPageView> | null>(null)
const viewport = ref<HTMLElement | null>(null)

let cache: LayoutCache = props.layoutCache ?? createLayoutCache()
let manifestController: AbortController | null = null
let layoutController: AbortController | null = null
/** The layout read of the current page (null without one, or when replaced). */
let layoutLoad: Promise<PageLayout | null> = Promise.resolve(null)
/** Increments with every focus request; an older one still waiting gives up. */
let focusGeneration = 0

const currentPage = computed<DocumentPage | null>(() => pages.value[currentIndex.value] ?? null)
const currentLabel = computed(() => currentPage.value?.label ?? String(currentIndex.value + 1))
const canZoom = computed(() => !!currentPage.value?.imageUrl && imageState.value === 'loaded')
const pageHighlights = computed(() => props.highlights.filter(h => h.pageId === currentPage.value?.pageId))

const layoutNotice = computed(() => {
  const page = currentPage.value
  if (!page?.imageUrl) return ''
  if (!page.layoutUrl) return 'No text lines for this page'
  if (layoutState.value === 'error') return 'The text lines could not be loaded'
  return ''
})

const pageSize = (page: DocumentPage) =>
  page.width && page.height ? { width: page.width, height: page.height } : null

async function loadManifest () {
  manifestController?.abort()
  const controller = new AbortController()
  manifestController = controller
  manifestState.value = 'loading'
  pages.value = []
  try {
    const result = await readDocumentPages(props.documentId, controller.signal)
    if (controller.signal.aborted) return
    pages.value = result.available ? result.pages : []
    manifestState.value = 'loaded'
    emit('loaded', { available: result.available, pageCount: pages.value.length })
    if (pages.value.length) showPage(indexOf(props.pageId) ?? 0, { force: true })
  } catch (e) {
    if (controller.signal.aborted || isAbortError(e)) return
    manifestError.value = await apiErrorMessage(e, 'The pages of this document could not be loaded.')
    manifestState.value = 'error'
  }
}

function indexOf (pageId: string | null | undefined): number | null {
  if (!pageId) return null
  const i = pages.value.findIndex(p => p.pageId === pageId)
  return i >= 0 ? i : null
}

async function loadLayout (page: DocumentPage): Promise<PageLayout | null> {
  layoutController?.abort()
  layout.value = null
  if (!page.layoutUrl) {
    layoutState.value = 'none'
    return null
  }
  const controller = new AbortController()
  layoutController = controller
  layoutState.value = 'loading'
  try {
    const result = await cache.get(page, controller.signal)
    // A newer page (or reload) took over meanwhile: never show this one's lines.
    if (controller !== layoutController || currentPage.value?.pageId !== page.pageId) return null
    layout.value = result
    layoutState.value = 'loaded'
    return result
  } catch (e) {
    if (controller.signal.aborted || isAbortError(e)) return null
    if (controller === layoutController) layoutState.value = 'error'
    return null
  }
}

function showPage (index: number, { force = false } = {}): Promise<PageLayout | null> {
  if (index < 0 || index >= pages.value.length) return Promise.resolve(null)
  // The page is shown already: its layout, also while it is still loading.
  if (!force && index === currentIndex.value && currentPage.value) return layoutLoad
  currentIndex.value = index
  activeLineId.value = null
  announcement.value = ''
  jumpText.value = ''
  jumpError.value = null
  imageState.value = 'loading'
  const page = pages.value[index]
  emit('pageChange', page, index)
  emit('update:pageId', page.pageId)
  layoutLoad = loadLayout(page)
  return layoutLoad
}

/** Show the page at `index` (user navigation; cancels a pending focus request). */
function goToPage (index: number) {
  focusGeneration++
  void showPage(index)
}

function jump () {
  const index = findPage(pages.value, jumpText.value)
  if (index === null) {
    jumpError.value = `No page "${jumpText.value.trim()}"`
    return
  }
  goToPage(index)
}

/**
 * An image-view focus request: open the page and bring the lines into view when they are not
 * visible enough (smart focus). Resolves true when the lines were found; false when the page
 * or line is unknown, has no layout, or a newer request or navigation replaced this one.
 */
async function focus (request: FocusRequest): Promise<boolean> {
  const generation = ++focusGeneration
  const index = indexOf(request.pageId)
  if (index === null) return false
  const pageLayout = await showPage(index)
  if (generation !== focusGeneration || !pageLayout) return !request.lineIds?.length && generation === focusGeneration
  if (!request.lineIds?.length) return true
  const ids = request.lineIds.filter(id => pageLayout.lines.some(l => l.id === id))
  if (!ids.length) return false
  setActiveLine(ids[0], false)
  // The view of a page that had no scan before is mounted on the next render.
  await nextTick()
  if (generation !== focusGeneration) return false
  view.value?.focusLines(ids, { start: request.start, end: request.end })
  return true
}

function setActiveLine (lineId: string, announce = true) {
  activeLineId.value = lineId
  const line = layout.value?.lines.find(l => l.id === lineId)
  if (announce && line && layout.value) {
    announcement.value = `Line ${line.index + 1} of ${layout.value.lines.length}: ${line.text}`
  }
}

function onLineClick (target: { lineId: string, offset?: number }) {
  if (!currentPage.value) return
  setActiveLine(target.lineId, false)
  emit('lineSelect', { pageId: currentPage.value.pageId, ...target })
}

function stepLine (step: 1 | -1) {
  const lines = layout.value?.lines ?? []
  const next = adjacentLine(lines, activeLineId.value, step)
  if (!next || !currentPage.value) return
  focusGeneration++
  setActiveLine(next.id)
  view.value?.focusLines([next.id])
  emit('lineFocus', { pageId: currentPage.value.pageId, lineId: next.id })
}

/** Typing targets keep their own keys (also inside the pane, e.g. the page field). */
function isEditable (target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el || typeof el.closest !== 'function') return false
  return !!el.closest('input, textarea, select, [contenteditable=""], [contenteditable="true"]')
}

function onKeydown (e: KeyboardEvent) {
  if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || isEditable(e.target)) return
  if (!pages.value.length) return
  let handled = true
  switch (e.key) {
    case 'ArrowDown': stepLine(1); break
    case 'ArrowUp': stepLine(-1); break
    case 'PageDown': goToPage(currentIndex.value + 1); break
    case 'PageUp': goToPage(currentIndex.value - 1); break
    case '+': case '=': view.value?.zoomIn(); break
    case '-': case '_': view.value?.zoomOut(); break
    case '0': view.value?.fit(); break
    default: handled = false
  }
  if (handled) e.preventDefault()
}

watch(() => props.documentId, () => {
  cache = props.layoutCache ?? createLayoutCache()
  focusGeneration++
  void loadManifest()
}, { immediate: true })

watch(() => props.pageId, (pageId) => {
  const index = indexOf(pageId)
  if (index !== null && index !== currentIndex.value) goToPage(index)
})

onBeforeUnmount(() => {
  manifestController?.abort()
  layoutController?.abort()
})

defineExpose({ focus, goToPage, currentPage, layout, view })
</script>

<style scoped>
.image-pane {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: #fff;
}

.image-pane__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px 4px;
  padding: 4px 8px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.12);
}

.image-pane__jump-input {
  width: 72px;
}

.image-pane__position {
  font-size: 0.85rem;
  white-space: nowrap;
}

.image-pane__zoom {
  min-width: 3.2em;
  text-align: center;
  font-size: 0.85rem;
}

.image-pane__notice {
  font-size: 0.8rem;
}

.image-pane__viewport {
  position: relative;
  flex: 1 1 auto;
  min-height: 160px;
}

.image-pane__viewport:focus-visible {
  outline: 2px solid var(--q-primary);
  outline-offset: -2px;
}

.image-pane__message {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 120px;
  padding: 16px;
  text-align: center;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
