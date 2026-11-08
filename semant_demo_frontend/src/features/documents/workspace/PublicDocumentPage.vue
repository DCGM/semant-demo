<template>
  <!-- The view fills the window below the app header; only its panes scroll (#600). -->
  <q-page class="public-document" :style-fn="fillHeight">
    <DocumentHeader
      :title="documentData ? (documentData.title || 'Untitled document') : (documentError ? 'Document not available' : '…')"
      :detail="detail"
      :document="documentData"
      :page-id="sync.currentPageId.value"
      :back="back"
    />

    <div v-if="documentError" class="text-negative q-pa-md" role="alert" data-testid="document-error">{{ documentError }}</div>
    <WorkspaceControls
      v-else
      :mode="workspace.shown.value"
      :narrow="workspace.narrow.value"
      :has-scan="workspace.hasScan.value"
      :notice="sync.notice.value"
      @update:mode="chooseMode"
    >
      <WhitespaceToggle v-model="preserveWhitespace" />
    </WorkspaceControls>

    <DocumentWorkspace
      v-if="!documentError"
      ref="workspacePane"
      v-model:narrow="workspace.narrow.value"
      :document-id="documentId"
      :mode="workspace.shown.value"
      :page-id="pageId"
      :document-title="documentData?.title ?? ''"
      :highlights="sync.scanHighlights.value"
      :layout-cache="layouts"
      @navigate="onNavigate"
      @page-change="onScanPage"
      @loaded="onLoaded"
      @line-select="sync.showLineInText"
      @line-focus="sync.showLineInText"
    >
      <section
        class="public-document__text"
        aria-label="Document text"
        data-testid="text-scroll"
        @wheel.passive="sync.cancel()"
        @touchstart.passive="sync.cancel()"
      >
        <div v-if="text.error.value" class="text-negative q-mb-md" role="alert">{{ text.error.value }}</div>
        <q-btn
          v-if="firstOrder > 0"
          flat dense no-caps color="primary" icon="expand_less" label="Earlier text"
          class="q-mb-sm" :loading="text.loading.value" data-testid="text-earlier"
          @click="text.extend('before')"
        />
        <DocumentTextPane
          ref="textPane"
          :chunks="text.chunks.value"
          :preserve-whitespace="preserveWhitespace"
          :active-range="activeRange"
          :active-approximate="!!sync.textFocus.value?.approximate"
          :page-marks="sync.pageMarks.value"
          @text-click="onTextClick"
          @select="onTextSelect"
        >
          <template #gap="{ paragraph }">
            <div class="public-document__gap text-grey-7">
              {{ missingChunksText(gapSize(paragraph)) }}
              <q-btn
                flat dense no-caps size="sm" color="primary" label="Show"
                :loading="text.loading.value" @click="text.fillGap(paragraph.gapAfter!)"
              />
            </div>
          </template>
        </DocumentTextPane>
        <div v-if="!text.chunks.value.length" class="text-grey-7" data-testid="text-empty" aria-live="polite">
          <template v-if="text.loading.value"><q-spinner size="1.2em" class="q-mr-sm" />Loading the text…</template>
          <template v-else>No text is shown yet.</template>
        </div>
        <q-btn
          v-if="text.chunks.value.length && text.hasAfter.value"
          flat dense no-caps color="primary" icon="expand_more" label="More text"
          class="q-mt-sm" :loading="text.loading.value" data-testid="text-later"
          @click="text.extend('after')"
        />
      </section>
    </DocumentWorkspace>

    <!-- The general right sidebar; the public view is read-only and has no collection tools. -->
    <RightSidebarPanel :id="DOCUMENT_SIDEBAR_PANELS.metadata" label="Document" icon="description" :order="2">
      <DocumentMetadataPanel v-if="documentData" :document="documentData" />
      <div v-else class="text-caption text-grey-7">{{ documentError || 'Loading the document…' }}</div>
    </RightSidebarPanel>
  </q-page>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, shallowRef, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { Document, DocumentPage } from 'src/generated/api'
import { errorStatus } from 'src/shared/api'
import RightSidebarPanel from 'src/app/sidebar/RightSidebarPanel.vue'
import { useDocumentsRepository } from 'src/features/documents/useDocumentsRepository'
import DocumentMetadataPanel from '../DocumentMetadataPanel.vue'
import { createLayoutCache } from '../scan/pageAssets'
import { selectionRange } from '../correspondence/layoutMap'
import { useDocumentText } from '../correspondence/useDocumentText'
import { useTextScanSync } from '../correspondence/useTextScanSync'
import { DOCUMENT_SIDEBAR_PANELS } from '../viewer/documentSidebar'
import DocumentTextPane from '../viewer/DocumentTextPane.vue'
import WhitespaceToggle from '../viewer/WhitespaceToggle.vue'
import type { DocumentTextPaneApi, TextSelection } from '../viewer/documentTextPane'
import { gapSize, missingChunksText, type ChunkRange, type TextPoint } from '../viewer/readerOffsets'
import DocumentHeader from './DocumentHeader.vue'
import DocumentWorkspace from './DocumentWorkspace.vue'
import { fillHeight } from './fillHeight'
import { returnLink } from './documentLink'
import { useWorkspaceMode } from './useWorkspaceMode'
import { parseMode, targetKey, withMode, withScanPage, type WorkspaceMode } from './workspaceMode'
import WorkspaceControls from './WorkspaceControls.vue'

// The public document view (#545, `/documents/:documentId`): the document's canonical text
// and its page scans in the paired workspace, with the text/scan correspondence (#544) and the
// document's metadata in the general right sidebar. Read-only and without a collection: no
// annotation is read and no editing state exists. Deep links: `?page=<page id>` opens a page
// and its text, `?chunk=<chunk id>&start=&end=` a passage (UTF-16 offsets in the chunk) and its
// lines, `?view=split|text|scan` the view, `?from=search|chat` the back link. A change of these
// on the same document (another link to it) is followed without reading the document again. The
// reader's own page changes in the scan viewer replace the passage with the page in the URL;
// the first page and pages opened for the text leave the link as it was.

/** The link's targets: a passage, or a page. */
const TARGETS = ['chunk', 'start', 'end', 'page'] as const
/** The targets a page the reader moved to replaces. */
const PASSAGE = ['chunk', 'start', 'end'] as const

const props = defineProps<{ documentId: string }>()

const route = useRoute()
const router = useRouter()
const documentData = shallowRef<Document | null>(null)
const documentError = ref('')
const textPane = ref<DocumentTextPaneApi | null>(null)
const workspacePane = ref<InstanceType<typeof DocumentWorkspace> | null>(null)
const pages = shallowRef<DocumentPage[]>([])
/** The text keeps its original whitespace (as in the collection reader), or collapses it. */
const preserveWhitespace = ref(true)
const layouts = shallowRef(createLayoutCache())
/** A passage opened by a deep link, until another interaction. */
const linkedRange = shallowRef<ChunkRange | null>(null)
/** The deep link has been handled: from then on, page changes in the scan viewer are followed. */
let following = false
/** Incremented by every link target: an older one still loading gives up. */
let targetGeneration = 0
/** The targets of the URL this page wrote itself (the reader's page change): not a new link. */
let ownTarget: string | null = null
let manifestReady: () => void = () => undefined
let manifest: Promise<void> = Promise.resolve()

const workspace = useWorkspaceMode(parseMode(route.query.view))
const text = useDocumentText(() => props.documentId)
const sync = useTextScanSync({
  pages,
  layouts: () => layouts.value,
  chunks: text.chunks,
  pageChunks: text.pageChunks,
  focusScan: (request) => workspacePane.value?.focus(request) ?? Promise.resolve(false),
  revealText: (at) => { textPane.value?.revealRange(at) }
})

const back = computed(() => returnLink(route.query.from))
const pageId = computed(() => typeof route.query.page === 'string' ? route.query.page : null)
const firstOrder = computed(() => text.chunks.value[0]?.order ?? 0)
const activeRange = computed(() => sync.textFocus.value?.range ?? linkedRange.value)
/** The subtitle and byline, after the title in the header. */
const detail = computed(() => {
  const d = documentData.value
  if (!d) return ''
  const byline = [d.author?.join(', '), d.yearIssued].filter(Boolean).join(', ') || 'Author and year unknown'
  return [d.subtitle, byline].filter(Boolean).join(' · ')
})

const queryNumber = (name: string) => {
  const v = route.query[name]
  return typeof v === 'string' && /^\d+$/.test(v) ? Number(v) : null
}

function chooseMode (mode: WorkspaceMode) {
  workspace.chosen.value = mode
  void router.replace({ query: withMode(route.query, mode) })
}

// The text shown again: the passage last focused from the scan comes into view.
watch(workspace.shown, async (mode, before) => {
  const at = sync.textFocus.value?.range ?? linkedRange.value
  if (before !== 'scan' || mode === 'scan' || !at) return
  await nextTick()
  textPane.value?.revealRange(at)
})

function onNavigate (page: DocumentPage) {
  const query = withScanPage(route.query, page.pageId, PASSAGE)
  ownTarget = targetKey(query, TARGETS)
  void router.replace({ query })
}

function onLoaded (info: { available: boolean, pages: DocumentPage[] }) {
  workspace.hasScan.value = info.available
  pages.value = info.pages
  manifestReady()
}

function onScanPage (page: DocumentPage, index: number) {
  if (following && !sync.isOwnPageChange(page.pageId)) linkedRange.value = null
  void sync.onScanPage(page, index, { follow: following })
}

function onTextClick (point: TextPoint | null) {
  if (!point) return
  linkedRange.value = null
  void sync.showTextOnScan({ chunkId: point.chunkId, start: point.charOffset, end: point.charOffset }, { markLine: true })
}

function onTextSelect ({ start, end }: TextSelection) {
  const range = selectionRange(start, end, text.chunks.value)
  if (!range) return
  linkedRange.value = null
  void sync.showTextOnScan(range)
}

/** Keys that scroll the page cancel a focus still on its way, like the wheel (not in the scan viewer or a field). */
function onKeydown (e: KeyboardEvent) {
  if (!['PageUp', 'PageDown', 'ArrowUp', 'ArrowDown', 'Home', 'End', ' '].includes(e.key)) return
  const target = e.target as HTMLElement | null
  if (target?.closest?.('[data-testid="workspace-scan"], input, textarea, [contenteditable]')) return
  sync.cancel()
}

async function open (documentId: string) {
  following = false
  linkedRange.value = null
  text.reset()
  layouts.value = createLayoutCache()
  manifest = new Promise(resolve => { manifestReady = resolve })
  ownTarget = null
  const generation = ++targetGeneration
  const chunkId = typeof route.query.chunk === 'string' ? route.query.chunk : null
  if (chunkId) {
    await showPassage(documentId, chunkId, generation)
    return
  }
  await manifest
  if (documentId !== props.documentId) return
  following = true
  const shown = workspacePane.value?.currentPage()
  const index = shown ? pages.value.findIndex(p => p.pageId === shown.pageId) : -1
  if (pageId.value && shown && index >= 0) await sync.onScanPage(shown, index)
  if (!text.chunks.value.length && documentId === props.documentId) await text.openStart()
}

/** A linked passage (`?chunk=&start=&end=`): its text in view and its lines on the scan. */
async function showPassage (documentId: string, chunkId: string, generation: number) {
  const chunk = await text.openChunk(chunkId)
  await manifest
  if (documentId !== props.documentId || generation !== targetGeneration) return
  following = true
  if (!chunk) return
  const length = chunk.text.length
  const start = Math.min(queryNumber('start') ?? 0, length)
  const end = Math.min(length, Math.max(start, queryNumber('end') ?? start))
  linkedRange.value = end > start ? { chunkId, start, end } : null
  await nextTick()
  textPane.value?.revealRange({ chunkId, start })
  await sync.showTextOnScan({ chunkId, start, end }, { markLine: end === start })
}

/**
 * Another link to this document (a query change; the page is reused): its passage is shown
 * with the text read so far. A page alone is opened by the scan viewer (`pageId`) and its
 * text followed from there.
 */
function followLink () {
  const generation = ++targetGeneration
  const chunkId = typeof route.query.chunk === 'string' ? route.query.chunk : null
  if (chunkId) {
    void showPassage(props.documentId, chunkId, generation)
    return
  }
  // The scan shows the linked page already: its text is shown as for a page change.
  const shown = workspacePane.value?.currentPage()
  const index = shown ? pages.value.findIndex(p => p.pageId === shown.pageId) : -1
  if (shown && index >= 0 && shown.pageId === pageId.value) {
    linkedRange.value = null
    void sync.onScanPage(shown, index)
  }
}

async function loadDocument (id: string) {
  documentData.value = null
  documentError.value = ''
  try {
    const doc = await useDocumentsRepository().getById(id)
    if (id === props.documentId) documentData.value = doc
  } catch (e) {
    if (id !== props.documentId) return
    documentError.value = errorStatus(e) === 404
      ? 'This document is not in the corpus.'
      : 'The document could not be loaded.'
  }
}

// Another document is read anew; another link to this one (a query-only navigation: Vue
// Router reuses the page) shows its target with the document read so far.
watch(() => [props.documentId, targetKey(route.query, TARGETS)] as const, ([id, key], before) => {
  if (!before || id !== before[0]) {
    void loadDocument(id)
    void open(id)
    return
  }
  if (route.name !== 'document' || key === before[1] || key === ownTarget) return
  ownTarget = null
  followLink()
}, { immediate: true })
watch(() => route.query.view, (view) => {
  if (route.name !== 'document') return
  workspace.chosen.value = parseMode(view) ?? 'split'
})

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  sync.cancel()
})
</script>

<style scoped>
.public-document {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #fff;
}

.public-document__text {
  position: relative;
  min-height: 100%;
  padding: 16px 20px 24px;
}

.public-document__gap {
  margin: 0 0 18px;
  font-size: 0.85rem;
}

@media (max-width: 599px) {
  .public-document__text {
    padding: 12px 12px 20px;
  }
}
</style>
