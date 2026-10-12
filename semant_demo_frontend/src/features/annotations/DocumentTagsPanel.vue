<template>
  <div>
    <div class="tags-toolbar">
      <q-btn
        flat
        dense
        no-caps
        icon="add"
        label="Add tag"
        class="add-tag-btn"
        @click="tagEditing.createTag()"
      />
      <div class="tags-toolbar-spacer" />
      <q-btn flat dense round size="xs" icon="visibility" @click="tagNav.showAllTags()">
        <q-tooltip>Show all</q-tooltip>
      </q-btn>
      <q-btn flat dense round size="xs" icon="visibility_off" @click="tagNav.hideAllTags(tags.map(t => t.id))">
        <q-tooltip>Hide all</q-tooltip>
      </q-btn>
    </div>
    <TagSearch ref="tagSearchRef" v-model="searchedTagName" class="q-mb-sm" />
    <div v-if="tagsLoading" class="flex flex-center q-pa-lg">
      <q-spinner size="2em" color="grey-6" />
    </div>
    <div v-else-if="!tags.length" class="text-body2 text-grey-6">
      No tags in this collection.
    </div>
    <div v-else-if="!filteredTags.length" class="text-body2 text-grey-6">
      No tags match "{{ searchedTagName }}".
    </div>
    <div v-else ref="tagsListRef" class="tags-list">
      <div
        v-for="tag in filteredTags"
        :key="tag.id"
        :data-tag-id="tag.id"
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
            @click="tagEditing.editTag(tag)"
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
          @update="(examples) => tagEditing.updateExamples(tag, examples)"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, nextTick, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { SpanType, Tag, WriteOutcome } from 'src/generated/api'
import { useApi } from 'src/shared/api'
import { describeIncomplete } from 'src/shared/writeOutcome'
import { useTagsStore } from './tagsStore'
import TagExamples from './TagExamples.vue'
import TagSearch from './TagSearch.vue'
import { useTagEditing } from './useTagEditing'
import { useTagNavigation } from './useTagNavigation'
import { useTagSearch } from './useTagSearch'
import useTagSpans from './useTagSpans'

// The tags of the collection in the document view: visibility, navigation between their
// annotations, editing, ordering and deleting a tag's approved annotations.
const props = defineProps<{
  collectionId: string
  documentId: string
}>()

const $q = useQuasar()
const { default: api } = useApi()
const { tags, loading: tagsLoading } = storeToRefs(useTagsStore())
const tagEditing = useTagEditing(() => props.collectionId)
const tagNav = useTagNavigation()
const tagSpans = useTagSpans()
const deletingTagSpansId = ref<string | null>(null)

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

// ── Tag search ──
const searchedTagName = ref('')
const tagSearchRef = ref<InstanceType<typeof TagSearch> | null>(null)
const { filteredTags } = useTagSearch(sortedTags, searchedTagName)

// Scroll the tags list to whichever tag becomes active (e.g. clicking a span
// marker in the gutter) so the panel follows the selection.
const tagsListRef = ref<HTMLElement | null>(null)

watch(() => tagNav.activeTagId.value, (tagId) => {
  if (!tagId) return
  void nextTick(() => {
    const el = tagsListRef.value?.querySelector<HTMLElement>(`[data-tag-id="${tagId}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
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

// The panel stays alive across tab switches (keep-alive) and keeps its order and search;
// another collection has other tags, so both start over.
watch(
  () => props.collectionId,
  () => {
    tagOrder.value = []
    orderSeeded.value = false
    searchedTagName.value = ''
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
      // Drop exactly the spans the backend deleted; failed ones stay visible.
      const deletedIds = new Set(result.succeeded ?? [])
      tagSpans.removeSpansLocally((s) => !!s.id && deletedIds.has(s.id))
      if (result.outcome === WriteOutcome.complete) {
        $q.notify({
          type: 'positive',
          message: `Deleted ${result.deleted} approved annotation${result.deleted === 1 ? '' : 's'} of "${tag.name}".`,
          timeout: 2500
        })
      } else {
        $q.notify({ type: 'negative', message: describeIncomplete(result, `Deleting annotations of "${tag.name}"`) })
      }
    } catch (e) {
      console.error('Failed to delete tag annotations', e)
      $q.notify({ type: 'negative', message: 'Failed to delete annotations.' })
    } finally {
      deletingTagSpansId.value = null
    }
  })
}

/** Focuses the tag search field (Ctrl+F in the document view). */
function focusSearch() {
  tagSearchRef.value?.focus()
}

defineExpose({ focusSearch })
</script>

<style scoped>
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
</style>
