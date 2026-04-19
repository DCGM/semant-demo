<template>
  <q-page class="q-pa-lg doc-page">
    <div class="page-shell">
      <q-card class="paper-card" :class="{ 'has-gutter': gutterItems.length > 0 }">
        <q-card-section class="paper-body">
          <div class="document-text" ref="documentTextRef" @mouseup="handleDocumentMouseUp($event)">
            <template v-for="(group, gIndex) in assembledParagraphs" :key="gIndex">
              <p>
                <ChunkAnnotator
                  v-for="chunk in group.chunks"
                  :key="chunk.id"
                  :chunk-id="chunk.id"
                  :text="chunk.text"
                  :spans="annotations.getProjectedSpans(chunk.id).filter(s => tagNav.isTagVisible(s.tagId))"
                  :selection="annotations.getLocalSelection(chunk.id)"
                  :available-tags="tags"
                  :highlight-span-id="hoveredSpanId"
                  @boundary-drag="onBoundaryDrag"
                />
              </p>
            </template>
          </div>
        </q-card-section>
        <q-inner-loading :showing="loading" />
        <error-display v-if="error" :error="error" />
      </q-card>

      <!-- Span gutter -->
      <div class="span-gutter-wrapper" v-if="gutterItems.length" @wheel.prevent="onGutterWheel">
        <div class="span-gutter" :style="{ width: gutterWidth + 'px', height: gutterHeight + 'px' }">
          <div
            v-for="item in gutterItems"
            :key="item.spanId"
            class="gutter-item"
            :class="{ 'is-active': hoveredSpanId === item.spanId }"
            :style="{
              top: item.top + 'px',
              height: item.height + 'px',
              left: item.column * 44 + 8 + 'px'
            }"
            @mouseenter="hoveredSpanId = item.spanId"
            @mouseleave="hoveredSpanId = null"
            @click.stop="onGutterClick(item, $event)"
          >
            <div class="gutter-line" :style="{ backgroundColor: (tagInfoMap[item.tagId] || { color: '#3b82f6' }).color }"></div>
            <div class="gutter-label" :style="{ backgroundColor: (tagInfoMap[item.tagId] || { color: '#3b82f6' }).color }">
              <q-icon :name="(tagInfoMap[item.tagId] || { pictogram: 'label' }).pictogram" size="10px" class="gutter-icon" />
              {{ (tagInfoMap[item.tagId] || { shorthand: '?' }).shorthand }}
            </div>
          </div>
        </div>
      </div>

      <!-- Context popover — shows near the mouse when selection or editing -->
      <Teleport to="body">
        <div
          v-if="annotations.hasSelection.value"
          class="annotation-popover"
          :style="popoverStyle"
          @mousedown.stop
        >
          <!-- Close button -->
          <q-btn
            flat dense round
            icon="close"
            size="sm"
            class="popover-close"
            @click="annotations.clearSelection()"
          />

          <!-- Tag picker mode -->
          <template v-if="showTagPicker">
            <div class="popover-header">
              <span class="popover-title">Select tag</span>
              <q-btn flat dense round icon="arrow_back" size="sm" @click="showTagPicker = false" />
            </div>
            <q-input
              v-model="tagSearch"
              dense
              outlined
              placeholder="Search tags..."
              class="tag-search"
              autofocus
              clearable
            >
              <template #prepend>
                <q-icon name="search" size="xs" />
              </template>
            </q-input>
            <div class="tag-list">
              <div
                v-for="tag in filteredTags"
                :key="tag.id"
                class="tag-row"
                :class="{ 'is-active': annotations.selection.value?.tagId === tag.id }"
                @click="onTagClick(tag.id)"
              >
                <span class="tag-dot" :style="{ backgroundColor: tag.color }"></span>
                <span class="tag-name">{{ tag.name }}</span>
                <span class="tag-shorthand">{{ tag.shorthand }}</span>
              </div>
              <div v-if="filteredTags.length === 0" class="tag-row-empty">No tags found</div>
            </div>
          </template>

          <!-- Default action mode -->
          <template v-else>
            <div class="popover-actions">
              <q-btn
                no-caps unelevated
                icon="sell"
                :label="annotations.isEditing.value ? 'Change tag' : 'Add tag'"
                color="primary"
                class="popover-btn"
                @click="showTagPicker = true"
              />
              <q-btn
                v-if="annotations.positionChanged.value"
                no-caps outline
                icon="save"
                label="Save"
                color="primary"
                class="popover-btn"
                @click="onSavePosition"
              />
              <q-btn
                v-if="annotations.isEditing.value"
                no-caps outline
                icon="delete"
                label="Delete"
                color="negative"
                class="popover-btn"
                @click="onDeleteSpan"
              />
              <!-- Cancel removed; close icon is at the top-right of the popover -->
            </div>
          </template>
        </div>
      </Teleport>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, ref, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import useChunks from 'src/composables/useChunks'
import useTags from 'src/composables/useTags'
import { useAnnotations } from 'src/composables/useAnnotations'
import { SpanType } from 'src/generated/api'
import { useTagNavigation } from 'src/composables/useTagNavigation'
import ChunkAnnotator from 'src/components/ChunkAnnotator.vue'
import ErrorDisplay from 'src/components/custom/ErrorDisplay.vue'

/**
 * Resolve a DOM node + offset into { chunkId, charOffset } by walking up
 * to the nearest [data-chunk-id] and [data-start] elements.
 */
function resolveSelectionEndpoint(
  node: Node,
  offset: number
): { chunkId: string; charOffset: number } | null {
  // Find the .text-segment with data-start
  let segmentEl: HTMLElement | null = null
  let current: Node | null = node
  while (current) {
    if (current instanceof HTMLElement && current.dataset.start !== undefined) {
      segmentEl = current
      break
    }
    current = current.parentElement
  }
  if (!segmentEl) return null

  // Find the parent [data-chunk-id]
  let chunkEl: HTMLElement | null = segmentEl
  while (chunkEl && !chunkEl.dataset.chunkId) {
    chunkEl = chunkEl.parentElement
  }
  if (!chunkEl) return null

  const chunkId = chunkEl.dataset.chunkId!
  const segStart = parseInt(segmentEl.dataset.start || '0', 10)
  const charOffset = node.nodeType === Node.TEXT_NODE ? segStart + offset : segStart

  return { chunkId, charOffset }
}

const props = defineProps<{
  collectionId: string
  documentId: string
}>()

const { chunks, loading, error, loadChunksInCollectionDocument } = useChunks()
const { tags, loadTagsByCollection } = useTags()

const annotations = useAnnotations(() => chunks.value)

// ── Gutter state ──

interface GutterItem {
  spanId: string
  chunkId: string
  tagId: string
  start: number
  end: number
  top: number
  height: number
  column: number
}

const COLUMN_WIDTH = 44
const documentTextRef = ref<HTMLElement | null>(null)
const hoveredSpanId = ref<string | null>(null)
const gutterItems = ref<GutterItem[]>([])
const showTagPicker = ref(false)
const tagSearch = ref('')

const filteredTags = computed(() => {
  const q = tagSearch.value.toLowerCase().trim()
  if (!q) return tags.value
  return tags.value.filter(t =>
    t.name.toLowerCase().includes(q) ||
    (t.shorthand && t.shorthand.toLowerCase().includes(q))
  )
})

// ── Popover positioning ──
const popoverPos = ref({ x: 0, y: 0 })

const popoverStyle = computed(() => ({
  position: 'fixed' as const,
  left: `${popoverPos.value.x}px`,
  top: `${popoverPos.value.y}px`,
  zIndex: 9999
}))

const updatePopoverPos = (e?: MouseEvent) => {
  if (e) {
    popoverPos.value = { x: e.clientX + 12, y: e.clientY - 8 }
  }
}
const tagInfoMap = computed(() => {
  const map: Record<string, { color: string; shorthand: string; pictogram: string }> = {}
  for (const tag of tags.value) {
    map[tag.id] = { color: tag.color, shorthand: tag.shorthand || tag.name.slice(0, 3), pictogram: tag.pictogram || 'label' }
  }
  return map
})

const gutterWidth = computed(() => {
  if (!gutterItems.value.length) return 0
  const maxCol = Math.max(...gutterItems.value.map(i => i.column))
  return (maxCol + 1) * COLUMN_WIDTH
})

const gutterHeight = computed(() => {
  if (!gutterItems.value.length) return 0
  return Math.max(...gutterItems.value.map(i => i.top + i.height))
})

function recalculateGutter() {
  const container = documentTextRef.value
  if (!container) { gutterItems.value = []; return }

  // Gutter wrapper is a flex sibling aligned to top of paper-card, so measure from card top
  const cardEl = container.closest('.paper-card') as HTMLElement | null
  if (!cardEl) { gutterItems.value = []; return }

  const cardRect = cardEl.getBoundingClientRect()
  const items: GutterItem[] = []

  for (const chunk of chunks.value) {
    const chunkSpans = annotations.spansByChunkId.value[chunk.id] || []

    for (const span of chunkSpans) {
      if (span.type === SpanType.neg || !span.id) continue
      if (!tagNav.isTagVisible(span.tagId)) continue

      let minTop = Infinity
      let maxBottom = -Infinity

      // Measure segments in the owning chunk and any subsequent chunks the span overflows into
      const startChunkIndex = chunks.value.indexOf(chunk)
      let remaining = span.end
      for (let ci = startChunkIndex; ci < chunks.value.length && remaining > 0; ci++) {
        const c = chunks.value[ci]
        const cEl = container.querySelector(`[data-chunk-id="${c.id}"]`) as HTMLElement | null
        if (!cEl) break

        const segEls = cEl.querySelectorAll<HTMLElement>('.text-segment')
        const offsetFromSpanChunk = ci === startChunkIndex ? 0 : chunks.value.slice(startChunkIndex, ci).reduce((sum, ch) => sum + ch.text.length, 0)
        const localStart = ci === startChunkIndex ? span.start : 0
        const localEnd = Math.min(c.text.length, span.end - offsetFromSpanChunk)

        for (const segEl of segEls) {
          const segStart = parseInt(segEl.dataset.start || '0')
          const segEnd = parseInt(segEl.dataset.end || '0')
          if (segStart < localEnd && segEnd > localStart) {
            const rect = segEl.getBoundingClientRect()
            minTop = Math.min(minTop, rect.top - cardRect.top)
            maxBottom = Math.max(maxBottom, rect.bottom - cardRect.top)
          }
        }

        remaining -= c.text.length
      }

      if (minTop === Infinity) continue

      items.push({
        spanId: span.id,
        chunkId: chunk.id,
        tagId: span.tagId,
        start: span.start,
        end: span.end,
        top: minTop,
        height: Math.max(maxBottom - minTop, 20),
        column: 0
      })
    }
  }

  // Assign columns (greedy — avoid vertical overlap)
  items.sort((a, b) => a.top - b.top)
  const columnBottoms: number[] = []

  for (const item of items) {
    let assigned = false
    for (let c = 0; c < columnBottoms.length; c++) {
      if (item.top >= columnBottoms[c] + 4) {
        columnBottoms[c] = item.top + item.height
        item.column = c
        assigned = true
        break
      }
    }
    if (!assigned) {
      item.column = columnBottoms.length
      columnBottoms.push(item.top + item.height)
    }
  }

  gutterItems.value = items
}

const onGutterClick = (item: GutterItem, e: MouseEvent) => {
  annotations.editSpan({
    id: item.spanId,
    chunkId: item.chunkId,
    tagId: item.tagId,
    start: item.start,
    end: item.end,
    originalStart: item.start,
    originalEnd: item.end,
    originalChunkId: item.chunkId
  })
  updatePopoverPos(e)
  showTagPicker.value = false
  tagSearch.value = ''

  // Sync nav index
  tagNav.syncIndex(item.tagId, item.spanId)
}

const onGutterWheel = (e: WheelEvent) => {
  const wrapper = (e.currentTarget as HTMLElement)
  wrapper.scrollLeft += e.deltaY
}

// ── Per-tag navigation (shared with drawer via composable) ──

const tagNav = useTagNavigation()

// Keep nav items in sync with gutter items
watch(gutterItems, (items) => {
  tagNav.setItems(items.map(i => ({
    spanId: i.spanId,
    chunkId: i.chunkId,
    tagId: i.tagId,
    start: i.start,
    end: i.end
  })))
})

// Register scroll & highlight callbacks
tagNav.onScroll((item) => {
  if (!documentTextRef.value) return
  const chunkEls = documentTextRef.value.querySelectorAll<HTMLElement>('[data-chunk-id]')
  for (const el of chunkEls) {
    if (el.dataset.chunkId !== item.chunkId) continue
    const segs = el.querySelectorAll<HTMLElement>('.text-segment')
    for (const seg of segs) {
      const s = parseInt(seg.dataset.start || '0')
      if (s >= item.start && s < item.end) {
        seg.scrollIntoView({ behavior: 'smooth', block: 'center' })
        return
      }
    }
  }
})
tagNav.onHighlight((spanId) => { hoveredSpanId.value = spanId })

/** Group chunks into paragraphs for rendering, but keep individual chunks accessible */
const assembledParagraphs = computed(() => {
  const paragraphs: { chunks: typeof chunks.value }[] = []
  let currentGroup: typeof chunks.value = []

  for (const chunk of chunks.value) {
    currentGroup.push(chunk)

    if (chunk.endParagraph) {
      paragraphs.push({ chunks: currentGroup })
      currentGroup = []
    }
  }

  if (currentGroup.length) {
    paragraphs.push({ chunks: currentGroup })
  }

  return paragraphs
})

const handleDocumentMouseUp = (e: MouseEvent) => {
  const domSelection = window.getSelection()
  if (!domSelection || domSelection.isCollapsed) return

  const range = domSelection.getRangeAt(0)
  const startPoint = resolveSelectionEndpoint(range.startContainer, range.startOffset)
  const endPoint = resolveSelectionEndpoint(range.endContainer, range.endOffset)

  if (!startPoint || !endPoint) return

  // Preserve editing context when re-selecting during edit mode
  const editingSpanId = annotations.selection.value?.editingSpanId
  const editingTagId = annotations.selection.value?.tagId

  if (startPoint.chunkId === endPoint.chunkId) {
    const start = Math.min(startPoint.charOffset, endPoint.charOffset)
    const end = Math.max(startPoint.charOffset, endPoint.charOffset)
    if (end > start) {
      annotations.setSelection(startPoint.chunkId, start, end, editingSpanId, editingTagId)
    }
  } else {
    annotations.setCrossChunkSelection(
      startPoint.chunkId, startPoint.charOffset,
      endPoint.chunkId, endPoint.charOffset,
      editingSpanId, editingTagId
    )
  }

  updatePopoverPos(e)
  showTagPicker.value = false
  tagSearch.value = ''
  domSelection.removeAllRanges()
}

const onTagClick = async (tagId: string) => {
  if (annotations.isEditing.value) {
    await annotations.updateSpanTag(tagId)
  } else {
    await annotations.createSpan(tagId)
  }
}

const onSavePosition = async () => {
  await annotations.updateSpanPosition()
}

const onBoundaryDrag = (payload: { chunkId: string; handle: 'start' | 'end'; charOffset: number }) => {
  annotations.adjustSelectionBoundary(payload.handle, payload.chunkId, payload.charOffset)
}

const onDeleteSpan = async () => {
  await annotations.deleteSpan()
}

// Load data + recalculate gutter
let resizeObserver: ResizeObserver | null = null

watch(
  () => chunks.value,
  async (newChunks) => {
    if (newChunks.length) {
      await annotations.loadAllSpans()
      await nextTick()
      recalculateGutter()
    }
  }
)

watch(
  () => annotations.spansByChunkId.value,
  () => nextTick(recalculateGutter),
  { deep: true }
)

watch(
  () => tagNav.hiddenTagIds.size,
  () => nextTick(recalculateGutter)
)

watch(
  () => annotations.selection.value?.tagId,
  (tagId) => tagNav.setActiveTagId(tagId ?? null)
)

// ── Dismiss on click-outside / Escape ──

const onClickOutside = (e: MouseEvent) => {
  if (!annotations.hasSelection.value) return
  const target = e.target as HTMLElement
  // Don't dismiss if clicking inside the popover or document text area
  const popover = document.querySelector('.annotation-popover')
  if (popover?.contains(target)) return
  if (documentTextRef.value?.contains(target)) return
  annotations.clearSelection()
}

const onEscape = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && annotations.hasSelection.value) {
    annotations.clearSelection()
  }
}

onMounted(async () => {
  await Promise.all([
    loadTagsByCollection(props.collectionId),
    loadChunksInCollectionDocument(props.collectionId, props.documentId)
  ])

  await nextTick()
  if (documentTextRef.value) {
    resizeObserver = new ResizeObserver(() => recalculateGutter())
    resizeObserver.observe(documentTextRef.value)
  }

  document.addEventListener('mousedown', onClickOutside)
  document.addEventListener('keydown', onEscape)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  document.removeEventListener('mousedown', onClickOutside)
  document.removeEventListener('keydown', onEscape)
})
</script>

<style scoped>
.doc-page {
  min-height: 100%;
  background: #eef2f7;
}

.page-shell {
  display: flex;
  gap: 0;
  align-items: stretch;
  border-radius: 16px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.08);
}

.paper-card {
  flex: 4;
  min-width: 0;
  min-height: calc(100vh - 160px);
  border-radius: 16px;
  background: #ffffff;
  box-shadow: none;
}

.paper-card.has-gutter {
  border-radius: 16px 0 0 16px;
}

.paper-header {
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
}

.paper-body {
  padding: 32px 32px 40px;
}

.document-text {
  max-width: none;
  margin: 0;
  font-size: 1.08rem;
  line-height: 2;
  color: rgba(15, 23, 42, 0.95);
}

.document-text p {
  margin: 0 0 18px;
}

@media (max-width: 1023px) {
  .paper-card {
    min-height: auto;
  }

  .paper-body {
    padding: 24px;
  }
}

@media (max-width: 599px) {
  .paper-body {
    padding: 20px 16px 24px;
  }

  .document-text {
    font-size: 1rem;
    line-height: 1.9;
  }
}

.annotation-popover {
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 8px;
  padding-top: 28px;
  background: #ffffff;
  border-radius: 10px;
  box-shadow: 0 8px 32px rgba(15, 23, 42, 0.18);
  border: 1px solid rgba(15, 23, 42, 0.08);
  min-width: 180px;
  max-width: 280px;
}

.popover-close {
  position: absolute;
  top: 4px;
  right: 6px;
  z-index: 1;
  font-size: 1.1em;
}

.popover-actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
}

.popover-btn {
  width: 100%;
  justify-content: flex-start;
  font-size: 0.85rem;
  font-weight: 500;
  min-height: 36px;
  border-radius: 8px;
  padding: 4px 14px;
}

.popover-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  margin-bottom: 2px;
}

.popover-title {
  font-size: 0.78rem;
  font-weight: 600;
  color: #64748b;
}

.tag-list {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 200px;
  overflow-y: auto;
}

.tag-search {
  width: 100%;
  margin-bottom: 4px;
}

.tag-search :deep(.q-field__control) {
  min-height: 32px;
}

.tag-row-empty {
  padding: 8px;
  text-align: center;
  font-size: 0.78rem;
  color: #94a3b8;
}

.tag-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.12s;
}

.tag-row:hover {
  background: #f1f5f9;
}

.tag-row.is-active {
  background: #e0f2fe;
}

.tag-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tag-name {
  font-size: 0.82rem;
  font-weight: 500;
  color: #1e293b;
  flex: 1;
}

.tag-shorthand {
  font-size: 0.72rem;
  color: #94a3b8;
  font-weight: 500;
}

/* ── Span gutter ── */

.span-gutter-wrapper {
  flex: 1;
  min-width: 60px;
  position: relative;
  overflow-x: auto;
  overflow-y: hidden;
  background: #ffffff;
  border-radius: 0 16px 16px 0;
  box-shadow: none;
}

.span-gutter-wrapper::-webkit-scrollbar {
  height: 6px;
}

.span-gutter-wrapper::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.04);
  border-radius: 3px;
  margin: 0 4px;
}

.span-gutter-wrapper::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.18);
  border-radius: 3px;
}

.span-gutter-wrapper::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.3);
}

.span-gutter {
  position: relative;
  min-width: 100%;
  padding: 0 4px;
}

.gutter-item {
  position: absolute;
  width: 40px;
  cursor: pointer;
}

.gutter-line {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  border-radius: 2px;
  opacity: 0.7;
  transition: opacity 0.15s;
}

.gutter-item:hover .gutter-line,
.gutter-item.is-active .gutter-line {
  opacity: 1;
}

.gutter-label {
  position: absolute;
  left: 8px;
  top: 0;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 0.65rem;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  color: #fff;
  white-space: nowrap;
  line-height: 1.4;
  opacity: 0.8;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.18);
  transition: opacity 0.15s;
}

.gutter-icon {
  opacity: 0.9;
}

.gutter-item:hover .gutter-label,
.gutter-item.is-active .gutter-label {
  opacity: 1;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
}
</style>
