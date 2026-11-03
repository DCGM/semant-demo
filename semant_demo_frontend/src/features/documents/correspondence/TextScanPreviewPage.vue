<template>
  <q-page class="text-scan-preview column no-wrap">
    <div class="text-scan-preview__header row items-center no-wrap q-px-md">
      <div class="col" style="min-width: 0">
        <div class="text-subtitle1 ellipsis" data-testid="text-scan-title">{{ title || documentId }}</div>
        <div class="text-caption text-grey-7 ellipsis" :title="sync.notice.value">
          <span v-if="sync.notice.value" aria-live="polite" data-testid="sync-notice">{{ sync.notice.value }}</span>
          <span v-else>Text and scan preview (#544), on its own until the document workspace (#545) uses it.</span>
        </div>
      </div>
    </div>

    <div class="text-scan-preview__body">
      <section
        ref="textScroll"
        class="text-scan-preview__text"
        aria-label="Document text"
        data-testid="text-scroll"
        @wheel.passive="sync.cancel()"
        @touchstart.passive="sync.cancel()"
        @keydown="onTextKeydown"
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
          :active-range="activeRange"
          :active-approximate="!!sync.textFocus.value?.approximate"
          :page-marks="sync.pageMarks.value"
          @text-click="onTextClick"
          @select="onTextSelect"
        >
          <template #gap="{ paragraph }">
            <div class="text-scan-preview__gap text-grey-7">
              {{ missingChunksText(gapSize(paragraph)) }}
              <q-btn
                flat dense no-caps size="sm" color="primary" label="Show"
                :loading="text.loading.value" @click="text.fillGap(paragraph.gapAfter!)"
              />
            </div>
          </template>
        </DocumentTextPane>
        <div v-if="!text.chunks.value.length && !text.loading.value" class="text-grey-7" data-testid="text-empty">
          No text is shown yet.
        </div>
        <q-btn
          v-if="text.chunks.value.length && text.hasAfter.value"
          flat dense no-caps color="primary" icon="expand_more" label="More text"
          class="q-mt-sm" :loading="text.loading.value" data-testid="text-later"
          @click="text.extend('after')"
        />
      </section>

      <div class="text-scan-preview__scan">
        <DocumentImagePane
          ref="scanPane"
          :document-id="documentId"
          :page-id="pageId"
          :document-title="title"
          :highlights="sync.scanHighlights.value"
          :layout-cache="layouts"
          @update:page-id="onPageId"
          @page-change="onScanPage"
          @loaded="onLoaded"
          @line-select="sync.showLineInText"
          @line-focus="sync.showLineInText"
        />
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { DocumentPage } from 'src/generated/api'
import { useDocumentsRepository } from 'src/features/documents/useDocumentsRepository'
import DocumentImagePane from '../scan/DocumentImagePane.vue'
import { createLayoutCache } from '../scan/pageAssets'
import DocumentTextPane from '../viewer/DocumentTextPane.vue'
import type { DocumentTextPaneApi, TextSelection } from '../viewer/documentTextPane'
import { gapSize, missingChunksText, type ChunkRange, type TextPoint } from '../viewer/readerOffsets'
import { selectionRange } from './layoutMap'
import { useDocumentText } from './useDocumentText'
import { useTextScanSync } from './useTextScanSync'

// The text and scan panes side by side with their correspondence (#544), on their own
// until the document workspace (#545) composes them in the application
// (src/router/previewRoutes.ts). Deep links: `?page=<page id>` opens a page and its text,
// `?chunk=<chunk id>&start=&end=` a passage (UTF-16 offsets in the chunk) and its lines.

const props = defineProps<{ documentId: string }>()

const route = useRoute()
const router = useRouter()
const title = ref('')
const textPane = ref<DocumentTextPaneApi | null>(null)
const scanPane = ref<InstanceType<typeof DocumentImagePane> | null>(null)
const textScroll = ref<HTMLElement | null>(null)
const pages = shallowRef<DocumentPage[]>([])
const layouts = shallowRef(createLayoutCache())
/** A passage opened by a deep link, until another interaction. */
const linkedRange = shallowRef<ChunkRange | null>(null)
/** The deep link has been handled: from then on, page changes in the scan viewer are followed. */
let following = false
let manifestReady: () => void = () => undefined
let manifest: Promise<void> = Promise.resolve()

const text = useDocumentText(() => props.documentId)
const sync = useTextScanSync({
  pages,
  layouts: () => layouts.value,
  chunks: text.chunks,
  pageChunks: text.pageChunks,
  focusScan: async (request) => (await scanPane.value?.focus(request)) ?? false,
  revealText: (at) => { textPane.value?.revealRange(at) }
})

const pageId = computed(() => typeof route.query.page === 'string' ? route.query.page : null)
const firstOrder = computed(() => text.chunks.value[0]?.order ?? 0)
const activeRange = computed(() => sync.textFocus.value?.range ?? linkedRange.value)

const queryNumber = (name: string) => {
  const v = route.query[name]
  return typeof v === 'string' && /^\d+$/.test(v) ? Number(v) : null
}

function onPageId (id: string) {
  if (id !== pageId.value) void router.replace({ query: { ...route.query, page: id } })
}

function onLoaded (info: { pages: DocumentPage[] }) {
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

/** Keys that scroll the text cancel a focus still on its way, like the wheel. */
function onTextKeydown (e: KeyboardEvent) {
  if (['PageUp', 'PageDown', 'ArrowUp', 'ArrowDown', 'Home', 'End', ' '].includes(e.key)) sync.cancel()
}

async function open (documentId: string) {
  following = false
  linkedRange.value = null
  text.reset()
  layouts.value = createLayoutCache()
  manifest = new Promise(resolve => { manifestReady = resolve })
  const chunkId = typeof route.query.chunk === 'string' ? route.query.chunk : null
  if (chunkId) {
    const chunk = await text.openChunk(chunkId)
    await manifest
    if (documentId !== props.documentId) return
    following = true
    if (!chunk) return
    const length = chunk.text.length
    const start = Math.min(queryNumber('start') ?? 0, length)
    const end = Math.max(start, queryNumber('end') ?? start)
    if (end > start) linkedRange.value = { chunkId, start, end }
    await nextTick()
    textPane.value?.revealRange({ chunkId, start })
    await sync.showTextOnScan({ chunkId, start, end }, { markLine: end === start })
    return
  }
  await manifest
  if (documentId !== props.documentId) return
  following = true
  const shown = scanPane.value?.currentPage
  const index = shown ? pages.value.findIndex(p => p.pageId === shown.pageId) : -1
  if (pageId.value && shown && index >= 0) await sync.onScanPage(shown, index)
  if (!text.chunks.value.length && documentId === props.documentId) await text.openStart()
}

watch(() => props.documentId, async (id) => {
  void open(id)
  title.value = ''
  try {
    const doc = await useDocumentsRepository().getById(id)
    if (id === props.documentId) title.value = doc.title ?? ''
  } catch {
    // The title is decoration here; the panes report their own errors.
  }
}, { immediate: true })
</script>

<style scoped>
.text-scan-preview {
  height: calc(100vh - 50px);
}

/* A fixed height: a new notice must not resize (and refit) the scan viewer. */
.text-scan-preview__header {
  flex: 0 0 auto;
  height: 56px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.12);
  overflow: hidden;
}

.text-scan-preview__body {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
}

.text-scan-preview__text {
  min-height: 0;
  overflow-y: auto;
  padding: 16px 24px;
  border-right: 1px solid rgba(0, 0, 0, 0.12);
}

.text-scan-preview__scan {
  min-height: 0;
}

.text-scan-preview__gap {
  margin: 0 0 18px;
  font-size: 0.85rem;
}

@media (max-width: 767px) {
  .text-scan-preview__body {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) minmax(0, 1fr);
  }

  .text-scan-preview__text {
    padding: 12px 16px;
    border-right: none;
    border-bottom: 1px solid rgba(0, 0, 0, 0.12);
  }
}
</style>
