<template>
  <q-layout
    ref="layoutRef"
    view="hHh LpR lff"
    container
    class="document-detail-layout"
    :style="layoutStyle"
  >
    <q-header class="doc-header q-pl-sm" bordered>
      <q-toolbar class="doc-header-toolbar">
        <q-btn flat round dense icon="arrow_back" :to="backToDocumentsRoute">
          <q-tooltip>Back to documents</q-tooltip>
        </q-btn>

        <div class="q-ml-sm" v-if="documentData">
          <div class="text-caption text-grey-6">Document detail</div>
          <div class="text-h5 text-weight-medium">{{ documentData.title || 'Untitled document' }}</div>
          <div v-if="documentData.subtitle" class="text-body2 text-grey-7 q-mt-xs">
            {{ documentData.subtitle }}
          </div>
        </div>

        <q-space />

        <div class="collection-context text-right q-pr-sm">
          <div class="text-caption text-grey-6">Collection</div>
          <div class="text-body1 text-weight-medium">{{ activeCollectionName }}</div>
        </div>

        <q-separator vertical inset class="q-mx-sm" />

        <q-btn
          flat round
          size="md"
          icon="menu"
          :color="drawerOpen ? undefined : 'primary'"
          @click="drawerOpen = !drawerOpen"
        >
          <q-tooltip>{{ drawerOpen ? 'Hide panel' : 'Show panel' }}</q-tooltip>
        </q-btn>
      </q-toolbar>
    </q-header>
    <q-drawer
      v-model="drawerOpen"
      side="right"
      :width="360"
      :breakpoint="0"
      bordered
      class="doc-info-drawer"
    >
      <div class="drawer-content">
        <div class="tabs-wrapper q-mx-md q-mt-md">
          <q-tabs v-model="drawerTab" dense align="justify" class="drawer-tabs" indicator-color="transparent">
            <q-tab name="tags" label="Tags" />
            <q-tab name="ai" label="AI assist" />
            <q-tab name="document" label="Document" />
          </q-tabs>
        </div>

        <q-tab-panels v-model="drawerTab" class="drawer-panels">
          <q-tab-panel name="tags" class="q-pa-md">
            <div class="tags-toolbar">
              <q-btn
                flat
                dense
                no-caps
                icon="add"
                label="Add tag"
                class="add-tag-btn"
                @click="handleCreateTag"
              />
              <div class="tags-toolbar-spacer" />
              <q-btn flat dense round size="xs" icon="visibility" @click="tagNav.showAllTags()">
                <q-tooltip>Show all</q-tooltip>
              </q-btn>
              <q-btn flat dense round size="xs" icon="visibility_off" @click="tagNav.hideAllTags(tags.map(t => t.id))">
                <q-tooltip>Hide all</q-tooltip>
              </q-btn>
            </div>
            <div v-if="tagsLoading" class="flex flex-center q-pa-lg">
              <q-spinner size="2em" color="grey-6" />
            </div>
            <div v-else-if="!tags.length" class="text-body2 text-grey-6">
              No tags in this collection.
            </div>
            <div v-else class="tags-list">
              <div
                v-for="tag in sortedTags"
                :key="tag.id"
                class="tag-card"
                :class="{
                  'is-active': tagNav.activeTagId.value === tag.id,
                  'is-hidden': !tagNav.isTagVisible(tag.id),
                  'is-dragging': dragTagId === tag.id,
                  'is-drop-before': dropTargetId === tag.id && dragTagId !== tag.id && dropHalf === 'before',
                  'is-drop-after': dropTargetId === tag.id && dragTagId !== tag.id && dropHalf === 'after'
                }"
                draggable="true"
                @dragstart="onDragStart(tag.id)"
                @dragover="onDragOver($event, tag.id)"
                @dragleave="onDragLeave(tag.id)"
                @drop.prevent="onDrop(tag.id)"
                @dragend="onDragEnd"
              >
                <div class="tag-card-header">
                  <q-btn
                    flat round dense
                    size="xs"
                    :icon="tagNav.isTagVisible(tag.id) ? 'visibility' : 'visibility_off'"
                    :class="tagNav.isTagVisible(tag.id) ? 'visibility-btn' : 'visibility-btn is-off'"
                    @click="tagNav.toggleTag(tag.id)"
                  />
                  <q-icon
                    :name="tag.pictogram || 'label'"
                    :style="{ color: tag.color || '#64748b' }"
                    size="20px"
                  />
                  <span class="tag-name">{{ tag.name }}</span>
                  <q-badge
                    v-if="tag.shorthand"
                    :label="tag.shorthand"
                    outline
                    :style="{ color: tag.color || '#64748b', borderColor: tag.color || '#64748b' }"
                    class="q-ml-auto"
                  />
                  <q-btn
                    flat
                    round
                    dense
                    size="sm"
                    icon="edit"
                    class="edit-tag-btn"
                    @click="handleEditTag(tag)"
                  >
                    <q-tooltip>Edit tag</q-tooltip>
                  </q-btn>
                  <q-btn
                    flat
                    round
                    dense
                    size="sm"
                    icon="delete_sweep"
                    class="delete-tag-spans-btn"
                    :disable="(posSpanCountByTag[tag.id] ?? 0) === 0 || deletingTagSpansId === tag.id"
                    :loading="deletingTagSpansId === tag.id"
                    @click="onDeleteAllTagSpans(tag)"
                  >
                    <q-tooltip>Delete all approved annotations of this tag in this document</q-tooltip>
                  </q-btn>
                </div>
                <!-- Span navigation -->
                <div v-if="tagNav.spanCount(tag.id) > 0" class="tag-nav-row">
                  <q-btn flat dense round icon="chevron_left" size="xs" @click="tagNav.navigate(tag.id, 'prev')" />
                  <span class="tag-nav-counter">
                    {{ tagNav.navIndex(tag.id) != null ? (tagNav.navIndex(tag.id)! + 1) : '–' }}/{{ tagNav.spanCount(tag.id) }}
                  </span>
                  <q-btn flat dense round icon="chevron_right" size="xs" @click="tagNav.navigate(tag.id, 'next')" />
                </div>
                <div v-if="tag.definition" class="tag-definition text-caption text-grey-7">
                  {{ tag.definition }}
                  <q-tooltip>{{ tag.definition }}</q-tooltip>
                </div>
                <TagExamples
                  :tag-name="tag.name"
                  :examples="tag.examples || []"
                  @update="(examples) => handleExamplesUpdate(tag, examples)"
                />
              </div>
            </div>
          </q-tab-panel>

          <q-tab-panel name="ai" class="q-pa-md ai-panel">
            <div class="ai-section-title">AI assistance</div>
            <div class="text-caption text-grey-7 q-mb-sm">
              Pick the tags the AI should look for in this document and choose a mode. Suggestions are shown as dashed grey markers in the text.
            </div>

            <div class="ai-section-label">Mode</div>
            <q-option-group
              v-model="aiMode"
              :options="aiModeOptions"
              type="radio"
              dense
              class="q-mb-md"
              :disable="aiAssist.isRunning.value"
            />

            <div class="ai-section-label">
              Tags
              <span class="text-caption text-grey-6 q-ml-xs">({{ selectedAiTagIds.length }}/{{ tags.length }})</span>
              <q-space />
              <q-btn flat dense no-caps size="sm" label="All" @click="selectAllAiTags" :disable="aiAssist.isRunning.value" />
              <q-btn flat dense no-caps size="sm" label="None" @click="clearAiTags" :disable="aiAssist.isRunning.value" />
            </div>
            <div v-if="!tags.length" class="text-body2 text-grey-6 q-mb-md">
              No tags in this collection yet.
            </div>
            <div v-else class="ai-tag-list q-mb-md">
              <div
                v-for="tag in tags"
                :key="tag.id"
                class="ai-tag-list-row"
              >
                <q-checkbox
                  :model-value="selectedAiTagIds.includes(tag.id)"
                  @update:model-value="(v) => toggleAiTag(tag.id, !!v)"
                  dense
                  size="sm"
                  :disable="aiAssist.isRunning.value"
                  class="ai-tag-checkbox"
                >
                  <template v-slot:default>
                    <span class="ai-tag-row">
                      <q-icon
                        :name="tag.pictogram || 'label'"
                        :style="{ color: tag.color || '#64748b' }"
                        size="16px"
                        class="q-mr-xs"
                      />
                      <span class="ai-tag-name">{{ tag.name }}</span>
                    </span>
                  </template>
                </q-checkbox>
                <div v-if="autoSpansByTag[tag.id]?.length" class="ai-tag-nav">
                  <q-btn
                    flat dense round size="xs"
                    icon="chevron_left"
                    :disable="autoSpansByTag[tag.id].length === 0"
                    @click="navigateAutoSpan(tag.id, 'prev')"
                  >
                    <q-tooltip>Previous suggestion</q-tooltip>
                  </q-btn>
                  <span class="ai-tag-nav-counter">
                    {{ autoSpanNavIndex(tag.id) != null ? (autoSpanNavIndex(tag.id)! + 1) : '–' }}/{{ autoSpansByTag[tag.id].length }}
                  </span>
                  <q-btn
                    flat dense round size="xs"
                    icon="chevron_right"
                    :disable="autoSpansByTag[tag.id].length === 0"
                    @click="navigateAutoSpan(tag.id, 'next')"
                  >
                    <q-tooltip>Next suggestion</q-tooltip>
                  </q-btn>
                </div>
              </div>
            </div>

            <div class="ai-actions q-mb-md">
              <q-btn
                v-if="!aiAssist.isRunning.value"
                color="primary"
                icon="auto_awesome"
                label="Run AI"
                no-caps
                :disable="!selectedAiTagIds.length"
                @click="onRunAi"
              />
              <q-btn
                v-else
                color="negative"
                icon="stop"
                label="Cancel"
                no-caps
                @click="aiAssist.cancel"
              />
              <q-btn
                outline
                color="negative"
                icon="delete_sweep"
                label="Clear unresolved"
                no-caps
                :loading="isBulkDeleting"
                :disable="!selectedAiTagIds.length || aiAssist.isRunning.value"
                @click="onBulkDelete"
              >
                <q-tooltip>
                  Delete every unresolved AI suggestion (auto spans) for the selected tags in this document.
                </q-tooltip>
              </q-btn>
            </div>
            <div v-if="lastDeletedCount != null" class="text-caption text-grey-7 q-mb-sm">
              Removed {{ lastDeletedCount }} unresolved suggestion(s).
            </div>

            <div v-if="aiAssist.isRunning.value || aiAssist.processedChunkCount.value > 0" class="ai-progress q-mb-sm">
              <q-spinner v-if="aiAssist.isRunning.value" color="primary" size="1.2em" class="q-mr-xs" />
              <span class="text-body2">
                Processed {{ aiAssist.processedChunkCount.value }} chunks,
                {{ aiAssist.totalSpansAdded.value }} suggestions.
              </span>
            </div>

            <div v-if="aiAssist.lastError.value" class="ai-error q-mb-sm">
              {{ aiAssist.lastError.value }}
            </div>

            <q-separator class="q-my-md" />

            <div class="ai-section-label">
              Pending suggestions
              <span class="text-caption text-grey-6 q-ml-xs">({{ pendingAutoSpans.length }})</span>
            </div>
            <div v-if="!pendingAutoSpans.length" class="text-body2 text-grey-6">
              No unresolved AI suggestions in the displayed chunks.
            </div>
            <template v-else>
              <div class="auto-span-bulk-bar">
                <q-checkbox
                  :model-value="allSuggestionsSelected"
                  :indeterminate-value="'mixed'"
                  :toggle-indeterminate="false"
                  dense
                  size="sm"
                  :disable="isBulkResolving"
                  @update:model-value="(v) => toggleSelectAllSuggestions(!!v)"
                >
                  <span class="text-caption text-grey-7">
                    {{ selectedSuggestionIds.size }} / {{ pendingAutoSpans.length }} selected
                  </span>
                </q-checkbox>
                <q-space />
                <q-btn
                  flat dense no-caps size="sm"
                  icon="check"
                  color="positive"
                  label="Approve"
                  :loading="isBulkResolving"
                  :disable="!selectedSuggestionIds.size || isBulkResolving"
                  @click="bulkResolveSelected(SpanType.pos)"
                >
                  <q-tooltip>Approve all selected suggestions</q-tooltip>
                </q-btn>
                <q-btn
                  flat dense no-caps size="sm"
                  icon="close"
                  color="negative"
                  label="Reject"
                  :loading="isBulkResolving"
                  :disable="!selectedSuggestionIds.size || isBulkResolving"
                  @click="bulkResolveSelected(SpanType.neg)"
                >
                  <q-tooltip>Reject all selected suggestions</q-tooltip>
                </q-btn>
              </div>
              <div class="auto-span-list">
              <div
                v-for="entry in pendingAutoSpans"
                :key="entry.span.id || `${entry.span.chunkId}:${entry.span.start}:${entry.span.end}:${entry.span.tagId}`"
                class="auto-span-card"
                :class="{
                  'is-busy': busyAutoSpanIds.has(entry.span.id || ''),
                  'is-highlighted': aiAssist.highlightedAutoSpanId.value && entry.span.id === aiAssist.highlightedAutoSpanId.value,
                  'is-selected': entry.span.id ? selectedSuggestionIds.has(entry.span.id) : false
                }"
                :ref="(el) => { if (entry.span.id) suggestionCardRefs[entry.span.id] = el as HTMLElement | null }"
                @click="onSuggestionClick(entry.span)"
              >
                <div class="auto-span-header">
                  <q-checkbox
                    :model-value="entry.span.id ? selectedSuggestionIds.has(entry.span.id) : false"
                    @update:model-value="(v) => toggleSuggestionSelection(entry.span, !!v)"
                    @click.stop
                    dense
                    size="xs"
                    :disable="isBulkResolving || busyAutoSpanIds.has(entry.span.id || '')"
                    class="q-mr-xs"
                  />
                  <q-icon
                    :name="entry.tag?.pictogram || 'label'"
                    :style="{ color: entry.tag?.color || '#64748b' }"
                    size="16px"
                    class="q-mr-xs"
                  />
                  <span class="auto-span-tag-name">{{ entry.tag?.name || 'Unknown tag' }}</span>
                  <q-badge
                    v-if="entry.span.confidence != null"
                    outline
                    :label="`${Math.round((entry.span.confidence as number) * 100)}%`"
                    class="auto-span-confidence q-ml-xs"
                  />
                  <q-space />
                  <q-btn
                    flat dense round size="xs"
                    icon="check"
                    color="positive"
                    :disable="busyAutoSpanIds.has(entry.span.id || '')"
                    @click.stop="approveAutoSpan(entry.span)"
                  >
                    <q-tooltip>Approve</q-tooltip>
                  </q-btn>
                  <q-btn
                    flat dense round size="xs"
                    icon="close"
                    color="negative"
                    :disable="busyAutoSpanIds.has(entry.span.id || '')"
                    @click.stop="rejectAutoSpan(entry.span)"
                  >
                    <q-tooltip>Reject</q-tooltip>
                  </q-btn>
                </div>
                <div
                  v-if="entry.span.reason"
                  class="auto-span-reason"
                >
                  {{ entry.span.reason }}
                  <q-tooltip
                    anchor="top middle"
                    self="bottom middle"
                    :delay="150"
                    max-width="320px"
                    class="auto-span-reason-tooltip"
                  >
                    {{ entry.span.reason }}
                  </q-tooltip>
                </div>
              </div>
              </div>
            </template>
          </q-tab-panel>

          <q-tab-panel v-if="documentData" name="document" class="q-pa-md">
            <div class="meta-row">
              <div class="meta-label">Authors</div>
              <div class="meta-value">{{ documentData.author?.join(', ') || '-' }}</div>
            </div>

            <div class="meta-row">
              <div class="meta-label">Year issued</div>
              <div class="meta-value">{{ documentData.yearIssued ?? '-' }}</div>
            </div>

            <div class="meta-row">
              <div class="meta-label">Language</div>
              <div class="meta-value">{{ documentData.language || '-' }}</div>
            </div>

            <div class="meta-row">
              <div class="meta-label">Publisher</div>
              <div class="meta-value">{{ documentData.publisher || '-' }}</div>
            </div>

            <div class="meta-row">
              <div class="meta-label">Place of publication</div>
              <div class="meta-value">{{ documentData.placeOfPublication || '-' }}</div>
            </div>

            <div class="meta-row">
              <div class="meta-label">Document type</div>
              <div class="meta-value">{{ documentData.documentType || '-' }}</div>
            </div>

            <div class="meta-row">
              <div class="meta-label">Keywords</div>
              <div class="meta-value">{{ documentData.keywords?.join(', ') || '-' }}</div>
            </div>
          </q-tab-panel>
        </q-tab-panels>
      </div>
    </q-drawer>

    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import useDocuments from 'src/composables/useDocuments'
import type { Document } from 'src/models/documents'
import { useRoute } from 'vue-router'
import useCollections from 'src/composables/useCollections'
import useTags from 'src/composables/useTags'
import useTagsDialog from 'src/composables/dialogs/useTagsDialog'
import type { PostTag, PatchTag, Tag } from 'src/models/tags'
import TagExamples from 'src/components/TagExamples.vue'
import { useTagNavigation } from 'src/composables/useTagNavigation'
import useAiAssistance, { type AiAssistanceMode } from 'src/composables/useAiAssistance'
import useTagSpans from 'src/composables/useTagSpans'
import { useApi } from 'src/composables/useApi'
import { SpanType } from 'src/generated/api'
import type { TagSpan } from 'src/models/tagSpans'

interface Props {
  collectionId: string
  documentId: string
}

const props = defineProps<Props>()
const route = useRoute()
const drawerOpen = ref(true)
const drawerTab = ref('tags')
const layoutRef = ref<unknown>(null)
const layoutHeight = ref<string>('auto')
const { activeDocument, loadDocument } = useDocuments()
const { activeCollection, loadCollection } = useCollections()
const { tags, loading: tagsLoading, loadTagsByCollection, createTag, updateTag } = useTags()
const { openTagsDialog } = useTagsDialog()
const $q = useQuasar()
const deletingTagSpansId = ref<string | null>(null)
const tagNav = useTagNavigation()
// ── Tag drag-reorder ──
const tagOrder = ref<string[]>([])
const dragTagId = ref<string | null>(null)
const dropTargetId = ref<string | null>(null)
const dropHalf = ref<'before' | 'after'>('before')

const sortedTags = computed(() => {
  if (!tagOrder.value.length) return tags.value
  const orderMap = new Map(tagOrder.value.map((id, i) => [id, i]))
  return [...tags.value].sort((a, b) => {
    const ai = orderMap.get(a.id) ?? Infinity
    const bi = orderMap.get(b.id) ?? Infinity
    return ai - bi
  })
})

// Sync tagOrder when tags change (new tags appended at end).
// Initial order favours tags that already have annotations — most occurrences
// first — so the most-used tags surface at the top on first render.
// Tags load before spans, so we keep re-seeding until either spans arrive
// (giving us real counts) or the user manually reorders.
const orderSeeded = ref(false)

function seedTagOrder(newTags: { id: string }[]) {
  const sorted = [...newTags].sort(
    (a, b) => tagNav.spanCount(b.id) - tagNav.spanCount(a.id)
  )
  tagOrder.value = sorted.map(t => t.id)
}

watch(tags, (newTags) => {
  const existing = new Set(tagOrder.value)
  const fresh = newTags.map(t => t.id).filter(id => !existing.has(id))
  if (!orderSeeded.value) {
    seedTagOrder(newTags)
  } else if (fresh.length) {
    tagOrder.value = [...tagOrder.value.filter(id => newTags.some(t => t.id === id)), ...fresh]
  }
})

// Re-seed once spans arrive, so initial sort reflects real occurrence counts.
watch(
  () => tagNav.groups.value.reduce((sum, g) => sum + g.items.length, 0),
  (total) => {
    if (orderSeeded.value) return
    if (total === 0) return
    seedTagOrder(tags.value)
    orderSeeded.value = true
  }
)

function onDragStart(tagId: string) {
  dragTagId.value = tagId
}

function onDragOver(e: DragEvent, tagId: string) {
  e.preventDefault()
  dropTargetId.value = tagId
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
  dropHalf.value = e.clientY < rect.top + rect.height / 2 ? 'before' : 'after'
}

function onDragLeave(tagId: string) {
  if (dropTargetId.value === tagId) dropTargetId.value = null
}

function onDrop(targetTagId: string) {
  if (!dragTagId.value || dragTagId.value === targetTagId) {
    dragTagId.value = null
    dropTargetId.value = null
    return
  }

  const order = [...tagOrder.value]
  const fromIdx = order.indexOf(dragTagId.value)
  let toIdx = order.indexOf(targetTagId)
  if (fromIdx === -1 || toIdx === -1) return

  order.splice(fromIdx, 1)
  // Adjust: if dropped on bottom half, insert after target
  if (dropHalf.value === 'after') {
    // After removing source, target may have shifted
    toIdx = order.indexOf(targetTagId)
    order.splice(toIdx + 1, 0, dragTagId.value)
  } else {
    toIdx = order.indexOf(targetTagId)
    order.splice(toIdx, 0, dragTagId.value)
  }
  tagOrder.value = order
  orderSeeded.value = true

  dragTagId.value = null
  dropTargetId.value = null
}

function onDragEnd() {
  dragTagId.value = null
  dropTargetId.value = null
}

// ── AI assistance ──
const aiAssist = useAiAssistance()
const tagSpans = useTagSpans()
const { default: api } = useApi()
const aiMode = ref<AiAssistanceMode>('optimized')
const aiModeOptions = [
  { label: 'Optimized (vector pre-filtering)', value: 'optimized' },
  { label: 'Thorough (every chunk in collection)', value: 'thorough' }
]
const selectedAiTagIds = ref<string[]>([])
const busyAutoSpanIds = ref<Set<string>>(new Set())
const isBulkDeleting = ref(false)
const lastDeletedCount = ref<number | null>(null)

// Track which drawer tab is active so the document page can hide auto spans
// outside of the AI assist tab.
watch(drawerTab, (val) => {
  aiAssist.aiTabActive.value = val === 'ai'
  if (val !== 'ai') aiAssist.highlightedAutoSpanId.value = null
}, { immediate: true })

onBeforeUnmount(() => {
  aiAssist.aiTabActive.value = false
  aiAssist.highlightedAutoSpanId.value = null
})

function onSuggestionClick(span: TagSpan) {
  if (!span.id) return
  aiAssist.highlightedAutoSpanId.value =
    aiAssist.highlightedAutoSpanId.value === span.id ? null : span.id
}

// Track card DOM nodes so we can scroll to whichever one is highlighted from
// the document side (i.e. the user clicked an auto span in the text).
const suggestionCardRefs = ref<Record<string, HTMLElement | null>>({})
watch(
  () => aiAssist.highlightedAutoSpanId.value,
  (id) => {
    if (!id) return
    void nextTick(() => {
      const el = suggestionCardRefs.value[id]
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    })
  }
)

function toggleAiTag(tagId: string, on: boolean) {
  if (on) {
    if (!selectedAiTagIds.value.includes(tagId)) selectedAiTagIds.value.push(tagId)
  } else {
    selectedAiTagIds.value = selectedAiTagIds.value.filter((id) => id !== tagId)
  }
}
function selectAllAiTags() {
  selectedAiTagIds.value = tags.value.map((t) => t.id)
}
function clearAiTags() {
  selectedAiTagIds.value = []
}

async function onRunAi() {
  if (!selectedAiTagIds.value.length) return
  await aiAssist.run({
    collectionId: props.collectionId,
    documentId: props.documentId,
    tagIds: [...selectedAiTagIds.value],
    mode: aiMode.value
  })
}

interface AutoSpanEntry {
  span: TagSpan
  tag: Tag | undefined
}

const tagsById = computed(() => {
  const m: Record<string, Tag> = {}
  for (const t of tags.value) m[t.id] = t
  return m
})

// Canonical pending auto spans (ordered by confidence desc) come from the
// composable; we just join in the tag for display.
const pendingAutoSpans = computed<AutoSpanEntry[]>(() =>
  aiAssist.pendingAutoSpans.value.map((span) => ({
    span,
    tag: tagsById.value[span.tagId]
  }))
)

// Group pending suggestions by tag id so each tag in the AI tag list can show
// per-tag navigation arrows and a counter.
const autoSpansByTag = computed<Record<string, TagSpan[]>>(() => {
  const out: Record<string, TagSpan[]> = {}
  for (const entry of pendingAutoSpans.value) {
    const list = out[entry.span.tagId] ?? (out[entry.span.tagId] = [])
    list.push(entry.span)
  }
  return out
})

function autoSpanNavIndex(tagId: string): number | null {
  const list = autoSpansByTag.value[tagId]
  if (!list?.length) return null
  const highlightedId = aiAssist.highlightedAutoSpanId.value
  if (!highlightedId) return null
  const idx = list.findIndex((s) => s.id === highlightedId)
  return idx === -1 ? null : idx
}

function navigateAutoSpan(tagId: string, direction: 'prev' | 'next') {
  const list = autoSpansByTag.value[tagId]
  if (!list?.length) return
  const current = autoSpanNavIndex(tagId)
  let nextIdx: number
  if (current == null) {
    nextIdx = direction === 'next' ? 0 : list.length - 1
  } else {
    nextIdx = direction === 'next' ? (current + 1) % list.length : (current - 1 + list.length) % list.length
  }
  const target = list[nextIdx]
  if (target.id) aiAssist.highlightedAutoSpanId.value = target.id
}

async function resolveSuggestion(span: TagSpan, type: SpanType) {
  if (!span.id) return
  busyAutoSpanIds.value.add(span.id)
  try {
    await aiAssist.resolveAutoSpan(span, type)
  } finally {
    busyAutoSpanIds.value.delete(span.id)
  }
}

const approveAutoSpan = (span: TagSpan) => resolveSuggestion(span, SpanType.pos)
const rejectAutoSpan = (span: TagSpan) => resolveSuggestion(span, SpanType.neg)

// ── Bulk approve / reject of selected suggestions ──
const selectedSuggestionIds = ref<Set<string>>(new Set())
const isBulkResolving = ref(false)

const allSuggestionsSelected = computed(() => {
  const ids = pendingAutoSpans.value
    .map((e) => e.span.id)
    .filter((id): id is string => !!id)
  if (!ids.length) return false
  return ids.every((id) => selectedSuggestionIds.value.has(id))
})

function toggleSuggestionSelection(span: TagSpan, on: boolean) {
  if (!span.id) return
  const next = new Set(selectedSuggestionIds.value)
  if (on) next.add(span.id)
  else next.delete(span.id)
  selectedSuggestionIds.value = next
}

function toggleSelectAllSuggestions(on: boolean) {
  if (on) {
    const ids = pendingAutoSpans.value
      .map((e) => e.span.id)
      .filter((id): id is string => !!id)
    selectedSuggestionIds.value = new Set(ids)
  } else {
    selectedSuggestionIds.value = new Set()
  }
}

// Drop ids from the selection once their spans disappear from the pending list
// (i.e. they got approved / rejected / deleted somewhere else).
watch(pendingAutoSpans, (entries) => {
  if (!selectedSuggestionIds.value.size) return
  const present = new Set(
    entries.map((e) => e.span.id).filter((id): id is string => !!id)
  )
  const next = new Set<string>()
  for (const id of selectedSuggestionIds.value) {
    if (present.has(id)) next.add(id)
  }
  if (next.size !== selectedSuggestionIds.value.size) {
    selectedSuggestionIds.value = next
  }
})

async function bulkResolveSelected(type: SpanType) {
  if (!selectedSuggestionIds.value.size) return
  // Snapshot the spans we want to act on (id -> chunkId) before any mutations
  // start removing them from the pending list.
  const targets: Array<{ id: string; chunkId: string }> = []
  const idSet = selectedSuggestionIds.value
  for (const entry of pendingAutoSpans.value) {
    if (entry.span.id && idSet.has(entry.span.id)) {
      targets.push({ id: entry.span.id, chunkId: entry.span.chunkId })
    }
  }
  if (!targets.length) return

  // Pre-compute which suggestion should be highlighted once these resolve.
  const targetIds = new Set(targets.map((t) => t.id))
  const nextHighlight =
    pendingAutoSpans.value.find((e) => e.span.id && !targetIds.has(e.span.id))?.span.id ?? null

  isBulkResolving.value = true
  for (const t of targets) busyAutoSpanIds.value.add(t.id)
  try {
    await tagSpans
      .bulkUpdateSpans(
        targets.map((t) => t.id),
        { type }
      )
      .catch((e: unknown) => {
        console.error('Bulk resolve failed', e)
      })
    aiAssist.highlightedAutoSpanId.value = nextHighlight
  } finally {
    for (const t of targets) busyAutoSpanIds.value.delete(t.id)
    isBulkResolving.value = false
    selectedSuggestionIds.value = new Set()
  }
}

async function onBulkDelete() {
  if (!selectedAiTagIds.value.length) return
  isBulkDeleting.value = true
  lastDeletedCount.value = null
  try {
    const result = await api.deleteAutoSpansApiAiAutoSpansDeletePost({
      deleteAutoSpansRequest: {
        collectionId: props.collectionId,
        documentId: props.documentId,
        tagIds: [...selectedAiTagIds.value]
      }
    })
    lastDeletedCount.value = result.deleted
    // Refresh auto spans currently in memory by dropping them from the store
    // for the affected (chunk, tag) pairs.
    const tagIdSet = new Set(selectedAiTagIds.value)
    tagSpans.removeSpansLocally((s) => s.type === SpanType.auto && tagIdSet.has(s.tagId))
  } catch (e) {
    console.error('Bulk delete of auto spans failed', e)
  } finally {
    isBulkDeleting.value = false
  }
}

// Per-tag count of approved (pos) spans in the currently loaded chunks. Used
// by the per-tag delete-sweep button which only wipes positives — auto
// suggestions and negative feedback are intentionally left alone.
const posSpanCountByTag = computed<Record<string, number>>(() => {
  const out: Record<string, number> = {}
  const byChunk = tagSpans.spansByChunkId.value
  for (const chunkId of Object.keys(byChunk)) {
    for (const s of byChunk[chunkId] || []) {
      if (s.type !== SpanType.pos) continue
      out[s.tagId] = (out[s.tagId] ?? 0) + 1
    }
  }
  return out
})

function onDeleteAllTagSpans(tag: Tag) {
  const count = posSpanCountByTag.value[tag.id] ?? 0
  if (!count) return
  $q.dialog({
    title: 'Delete approved annotations',
    message: `Delete all ${count} approved annotation${count === 1 ? '' : 's'} of "${tag.name}" in this document? Negative feedback and unresolved AI suggestions will be kept. This cannot be undone.`,
    cancel: true,
    persistent: true,
    ok: { label: 'Delete', color: 'negative', flat: false }
  }).onOk(async () => {
    deletingTagSpansId.value = tag.id
    try {
      const result = await api.deleteSpansForTagsInDocumentApiTagSpansInDocumentDeletePost({
        deleteSpansForTagsRequest: {
          collectionId: props.collectionId,
          documentId: props.documentId,
          tagIds: [tag.id]
        }
      })
      // Drop only approved spans for this tag from the in-memory store —
      // mirrors what the backend just did.
      tagSpans.removeSpansLocally((s) => s.tagId === tag.id && s.type === SpanType.pos)
      $q.notify({
        type: 'positive',
        message: `Deleted ${result.deleted} approved annotation${result.deleted === 1 ? '' : 's'} of "${tag.name}".`,
        timeout: 2500
      })
    } catch (e) {
      console.error('Failed to delete tag annotations', e)
      $q.notify({ type: 'negative', message: 'Failed to delete annotations.' })
    } finally {
      deletingTagSpansId.value = null
    }
  })
}

const handleCreateTag = () => {
  openTagsDialog({ dialogType: 'CREATE' }).onOk(async (tagData: PostTag) => {
    await createTag(props.collectionId, tagData)
    await loadTagsByCollection(props.collectionId)
  })
}

const handleEditTag = (tag: Tag) => {
  openTagsDialog({ dialogType: 'EDIT', tag }).onOk(async (updatedData: PatchTag) => {
    await updateTag(tag.id, updatedData)
    await loadTagsByCollection(props.collectionId)
  })
}

const handleExamplesUpdate = async (tag: Tag, examples: string[]) => {
  await updateTag(tag.id, { examples })
  await loadTagsByCollection(props.collectionId)
}

const documentData = computed<Document>(() => activeDocument.value!)

const activeCollectionName = computed(() => {
  if (activeCollection.value?.id === props.collectionId) {
    return activeCollection.value.name
  }
  return 'Unknown collection'
})

const layoutStyle = computed(() => ({
  '--document-layout-height': layoutHeight.value
}))

const backToDocumentsRoute = computed(() => ({
  name: 'collectionDocumentsTagging',
  params: {
    collectionId:
      props.collectionId ||
      (typeof route.params.collectionId === 'string' ? route.params.collectionId : '')
  }
}))

const getLayoutElement = (): HTMLElement | null => {
  const target = layoutRef.value as { $el?: Element } | HTMLElement | null

  if (!target) {
    return null
  }

  if (target instanceof HTMLElement) {
    return target
  }

  if (target.$el instanceof HTMLElement) {
    return target.$el
  }

  return null
}

const updateLayoutHeight = () => {
  const layoutElement = getLayoutElement()
  if (!layoutElement) {
    return
  }

  const { top } = layoutElement.getBoundingClientRect()
  const normalizedTop = Math.max(top, 0)
  const computedHeight = Math.max(window.innerHeight - normalizedTop, 320)

  layoutHeight.value = `${Math.round(computedHeight)}px`
}

watch(
  () => props.documentId,
  async (documentId) => {
    // Reset shared AI assistance state so stale "Processed N chunks" / pending
    // suggestions from the previous document don't leak into the new one.
    aiAssist.reset()
    selectedSuggestionIds.value = new Set()
    lastDeletedCount.value = null
    tagSpans.clearAll()
    await loadDocument(documentId)
  },
  { immediate: true }
)

watch(
  () => props.collectionId,
  async (collectionId) => {
    await loadCollection(collectionId)
    await loadTagsByCollection(collectionId)
  },
  { immediate: true }
)

onMounted(async () => {
  await nextTick()
  updateLayoutHeight()

  window.addEventListener('resize', updateLayoutHeight, { passive: true })
  window.addEventListener('scroll', updateLayoutHeight, { passive: true })
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateLayoutHeight)
  window.removeEventListener('scroll', updateLayoutHeight)
})
</script>

<style scoped>
.document-detail-layout {
  height: var(--document-layout-height, auto);
  min-height: 0;
  background: #eef2f7;
}

.doc-header {
  background: #ffffff;
  color: #1f2a37;
  border-bottom: 1px solid rgba(15, 23, 42, 0.1);
}

.doc-header-toolbar {
  min-height: 88px;
}

.collection-context {
  max-width: 360px;
}

.doc-header :deep(.q-btn) {
  color: #334155;
}

.doc-info-drawer {
  background: #f8fafc;
  color: #1f2937;
}

.drawer-content {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.tabs-wrapper {
  flex-shrink: 0;
  background: rgba(15, 23, 42, 0.06);
  border-radius: 10px;
  padding: 4px;
}

.drawer-tabs {
  border-radius: 8px;
}

.drawer-tabs :deep(.q-tab) {
  border-radius: 7px;
  min-height: 32px;
}

.drawer-tabs :deep(.q-tab--active) {
  background: #ffffff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.1);
}

.meta-row {
  padding: 12px 0;
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
}

.meta-row:last-child {
  border-bottom: 0;
}

.meta-label {
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgba(71, 85, 105, 0.85);
  margin-bottom: 4px;
}

.meta-value {
  font-size: 0.98rem;
  color: rgba(15, 23, 42, 0.95);
  word-break: break-word;
}

.tags-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tag-card {
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.03);
  border: 1px solid rgba(15, 23, 42, 0.06);
  min-height: 80px;
  cursor: grab;
  transition: opacity 0.15s, border-color 0.15s;
}

.tag-card:active {
  cursor: grabbing;
}

.tag-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tag-name {
  font-size: 0.95rem;
  font-weight: 500;
  color: rgba(15, 23, 42, 0.9);
}

.tag-definition {
  margin-top: 4px;
  padding-left: 28px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tags-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 8px;
}

.tags-toolbar-spacer {
  flex: 1;
}

.add-tag-btn {
  color: #475569;
  font-size: 0.85rem;
}

.visibility-btn {
  color: #94a3b8;
  transition: color 0.15s;
}

.visibility-btn:hover {
  color: #475569;
}

.visibility-btn.is-off {
  color: #cbd5e1;
}

.tag-card.is-active {
  border-color: #3b82f6;
  box-shadow: 0 0 0 1px #3b82f6;
}

.tag-card.is-hidden {
  opacity: 0.45;
}

.tag-card.is-dragging {
  opacity: 0.4;
}

.tag-card.is-drop-before {
  border-top: 2px solid #3b82f6;
  margin-top: -1px;
}

.tag-card.is-drop-after {
  border-bottom: 2px solid #3b82f6;
  margin-bottom: -1px;
}

.edit-tag-btn {
  color: #94a3b8;
  opacity: 0;
  transition: opacity 0.15s;
}

.tag-card:hover .edit-tag-btn {
  opacity: 1;
}

.delete-tag-spans-btn {
  color: #94a3b8;
  opacity: 0 !important;
  transition: opacity 0.15s, color 0.15s;
}

.tag-card:hover .delete-tag-spans-btn {
  opacity: 1 !important;
}

.delete-tag-spans-btn:hover {
  color: #dc2626;
}

.tag-card:hover .delete-tag-spans-btn.disabled,
.tag-card:hover .delete-tag-spans-btn[disabled] {
  color: #cbd5e1;
  opacity: 0.6 !important;
}

.tag-nav-row {
  display: flex;
  align-items: center;
  gap: 2px;
  padding-left: 28px;
  margin-top: 2px;
}

.tag-nav-counter {
  font-size: 0.75rem;
  font-weight: 600;
  color: #64748b;
  min-width: 36px;
  text-align: center;
}

/* ── AI assistance tab ── */
.ai-panel {
  display: block;
}

.ai-panel .ai-tag-list,
.ai-panel .auto-span-list {
  flex: none;
}

.ai-section-title {
  font-size: 1.05rem;
  font-weight: 600;
  color: #1f2a37;
  margin-bottom: 6px;
}

.ai-section-label {
  display: flex;
  align-items: center;
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(71, 85, 105, 0.85);
  margin-top: 4px;
  margin-bottom: 6px;
}

.ai-tag-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 240px;
  overflow-y: auto;
  padding: 4px 6px;
  background: rgba(15, 23, 42, 0.03);
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 6px;
}

.ai-tag-row {
  display: inline-flex;
  align-items: center;
  font-size: 0.9rem;
}

.ai-tag-list-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.ai-tag-checkbox {
  flex: 1 1 auto;
  min-width: 0;
}

.ai-tag-nav {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  color: rgba(71, 85, 105, 0.85);
}

.ai-tag-nav-counter {
  font-size: 0.75rem;
  font-variant-numeric: tabular-nums;
  min-width: 28px;
  text-align: center;
  color: rgba(71, 85, 105, 0.85);
}

.ai-tag-name {
  color: rgba(15, 23, 42, 0.9);
}

.ai-actions {
  display: flex;
  gap: 8px;
}

.ai-progress {
  display: flex;
  align-items: center;
  color: #475569;
}

.ai-error {
  color: #b91c1c;
  font-size: 0.85rem;
  background: rgba(185, 28, 28, 0.08);
  border-radius: 6px;
  padding: 6px 8px;
}

.auto-span-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  /* Cap height with an internal scrollbar so the section below
     ("Clear unresolved suggestions") stays reachable without scrolling
     past every individual suggestion. */
  max-height: 360px;
  overflow-y: auto;
  padding-right: 4px;
}

.auto-span-bulk-bar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 4px 6px 4px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
  margin-bottom: 6px;
}

.auto-span-card.is-selected {
  border-style: solid;
  border-color: rgba(37, 99, 235, 0.5);
  background: rgba(37, 99, 235, 0.06);
}

.auto-span-card.is-selected.is-highlighted {
  border-color: rgba(37, 99, 235, 0.7);
  background: rgba(37, 99, 235, 0.12);
}

.auto-span-card {
  border: 1px dashed rgba(15, 23, 42, 0.18);
  background: rgba(255, 255, 255, 0.6);
  border-radius: 6px;
  padding: 6px 8px;
  transition: opacity 0.15s, box-shadow 0.15s, border-color 0.15s, background 0.15s;
  cursor: pointer;
}

.auto-span-card:hover {
  border-color: rgba(15, 23, 42, 0.32);
  background: rgba(255, 255, 255, 0.85);
}

.auto-span-card.is-highlighted {
  border-style: solid;
  border-color: rgba(15, 23, 42, 0.4);
  background: rgba(15, 23, 42, 0.06);
}

.auto-span-card.is-busy {
  opacity: 0.5;
  pointer-events: none;
}

.auto-span-header {
  display: flex;
  align-items: center;
}

.auto-span-tag-name {
  font-size: 0.9rem;
  font-weight: 500;
  color: rgba(15, 23, 42, 0.9);
}

.auto-span-snippet {
  font-size: 0.78rem;
  color: rgba(71, 85, 105, 0.9);
  margin-top: 2px;
  padding-left: 22px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.auto-span-reason {
  margin-top: 4px;
  padding-left: 22px;
  font-size: 0.82rem;
  font-style: italic;
  color: rgba(71, 85, 105, 0.85);
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.auto-span-confidence {
  font-size: 0.7rem;
  font-weight: 600;
  color: #64748b;
  border-color: #94a3b8;
}

.auto-span-reason-tooltip {
  font-size: 0.85rem;
  line-height: 1.4;
  white-space: pre-wrap;
  background: rgba(15, 23, 42, 0.92);
}
</style>
