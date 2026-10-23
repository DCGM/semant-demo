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
      <q-btn
        flat dense round size="xs" icon="sort_by_alpha"
        class="sort-btn" :class="{ 'is-on': sortMode === 'name' }"
        aria-label="Sort tags by name"
        :aria-pressed="sortMode === 'name'"
        @click="sortBy('name')"
      >
        <q-tooltip>Sort by name</q-tooltip>
      </q-btn>
      <q-btn
        flat dense round size="xs" icon="format_list_numbered"
        class="sort-btn" :class="{ 'is-on': sortMode === 'count' }"
        aria-label="Sort tags by number of annotations"
        :aria-pressed="sortMode === 'count'"
        @click="sortBy('count')"
      >
        <q-tooltip>Sort by number of approved annotations</q-tooltip>
      </q-btn>
      <q-separator vertical class="q-mx-xs" />
      <q-btn flat dense round size="xs" icon="visibility" aria-label="Show all tags" @click="tagNav.showAllTags()">
        <q-tooltip>Show all</q-tooltip>
      </q-btn>
      <q-btn flat dense round size="xs" icon="visibility_off" aria-label="Hide all tags" @click="tagNav.hideAllTags(tags.map(t => t.id))">
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
        :style="{ '--tag-color': tag.color || '#64748b' }"
        :class="{
          'is-active': tagNav.activeTagId.value === tag.id,
          'is-focused': tagNav.focusedTagId.value === tag.id,
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
        @click="onCardClick($event, tag.id)"
      >
        <div class="tag-card-header">
          <q-btn
            flat round dense
            size="xs"
            :icon="tagNav.isTagVisible(tag.id) ? 'visibility' : 'visibility_off'"
            :class="tagNav.isTagVisible(tag.id) ? 'visibility-btn' : 'visibility-btn is-off'"
            @click="tagNav.toggleTag(tag.id)"
          />
          <!-- The whole card focuses the tag on click; this is its keyboard target. -->
          <span
            class="tag-focus-target"
            role="button"
            tabindex="0"
            :aria-pressed="tagNav.focusedTagId.value === tag.id"
            :aria-label="`Tag with ${tag.name}`"
            :title="tagNav.focusedTagId.value === tag.id ? 'Stop tagging with this tag' : 'Tag new selections with this tag'"
            @keydown.enter.prevent="tagNav.toggleFocusedTag(tag.id)"
            @keydown.space.prevent="tagNav.toggleFocusedTag(tag.id)"
          >
            <q-icon
              :name="tag.pictogram || 'label'"
              :style="{ color: tag.color || '#64748b' }"
              size="20px"
            />
            <span class="tag-name">{{ tag.name }}</span>
          </span>
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
import { byName, getTagSortMode, setTagSortMode, type TagSortMode } from './tagSortMode'
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

// Per-tag count of approved (pos) spans in the currently loaded chunks. Used to sort by
// number of annotations and by the per-tag delete-sweep button, which only wipes
// positives — auto suggestions and negative feedback are intentionally left alone.
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

// ── Tag order: by name, by number of annotations, or as dragged ──
const tagOrder = ref<string[]>([])
const dragTagId = ref<string | null>(null)
const dropTargetId = ref<string | null>(null)
const dropHalf = ref<'before' | 'after'>('before')
const sortMode = ref<TagSortMode>(getTagSortMode())

const sortedTags = computed(() => {
  // By name stays sorted as tags are added or renamed.
  if (sortMode.value === 'name') return [...tags.value].sort(byName)
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

// By number of annotations, the order is taken when chosen and once the document's spans
// have loaded (also when there are none), not on every change, so a tag doesn't move away
// while it is being used. Until then, a change of the tags sorts them again.
const orderSeeded = ref(false)

function sortByCount() {
  const counts = posSpanCountByTag.value
  tagOrder.value = [...tags.value]
    .sort((a, b) => (counts[b.id] ?? 0) - (counts[a.id] ?? 0) || byName(a, b))
    .map(t => t.id)
}

/** Sorts the tags by `mode`; choosing the current mode again sorts again. */
function sortBy(mode: Exclude<TagSortMode, 'custom'>) {
  sortMode.value = mode
  setTagSortMode(mode)
  orderSeeded.value = true
  if (mode === 'count') sortByCount()
}

watch(tags, (newTags) => {
  const existing = new Set(tagOrder.value)
  const fresh = newTags.map(t => t.id).filter(id => !existing.has(id))
  if (!orderSeeded.value || !tagOrder.value.length) {
    sortByCount()
  } else if (fresh.length) {
    tagOrder.value = [...tagOrder.value.filter(id => newTags.some(t => t.id === id)), ...fresh]
  }
})

// Sort again once the spans have loaded, so the first order reflects real counts.
watch(tagSpans.loading, (loading) => {
  if (loading || orderSeeded.value) return
  sortByCount()
  orderSeeded.value = true
})

// The panel stays alive while another sidebar panel is shown and keeps its order and search;
// another collection has other tags, so both start over (the sort mode is kept).
watch(
  () => props.collectionId,
  () => {
    tagOrder.value = []
    orderSeeded.value = false
    searchedTagName.value = ''
    if (sortMode.value === 'custom') sortMode.value = getTagSortMode()
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

  // Dragging starts from the order shown and leaves it as dragged.
  const order = sortedTags.value.map(t => t.id)
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
  sortMode.value = 'custom'

  dragTagId.value = null
  dropTargetId.value = null
}

function onDragEnd() {
  dragTagId.value = null
  dropTargetId.value = null
}

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

// A click on the card (not on one of its buttons, its annotation navigation, examples or
// fields, nor the end of selecting its text) focuses its tag in the reader (#479); a click
// on the focused tag's card ends it.
function onCardClick(e: MouseEvent, tagId: string) {
  const target = e.target as HTMLElement
  if (target.closest('button, a, input, textarea, .q-btn, .q-field, .tag-nav-row, .tag-examples')) return
  if (!(window.getSelection()?.isCollapsed ?? true)) return
  tagNav.toggleFocusedTag(tagId)
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
  /* A click focuses the tag; the card can still be dragged to reorder. */
  cursor: pointer;
  transition: opacity 0.15s, border-color 0.15s, background-color 0.15s;
}

.tag-card:active {
  cursor: grabbing;
}

.tag-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tag-focus-target {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  border-radius: 4px;
}

.tag-focus-target:focus-visible {
  outline: 2px solid #3b82f6;
  outline-offset: 2px;
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

.sort-btn {
  color: #94a3b8;
}

.sort-btn.is-on {
  color: #1d4ed8;
  background: #eff6ff;
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

/* The focused tag (#479): its spans stay highlighted in the reader, new selections get it. */
.tag-card.is-focused {
  border-color: var(--tag-color);
  box-shadow: 0 0 0 1px var(--tag-color);
  background: color-mix(in srgb, var(--tag-color) 12%, #ffffff);
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
