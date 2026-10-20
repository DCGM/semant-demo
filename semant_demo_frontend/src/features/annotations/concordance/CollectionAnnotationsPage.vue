<template>
  <q-page class="collection-annotations q-px-md q-pb-lg" data-testid="collection-annotations">
    <ConcordanceToolbar
      :filters="store.filters"
      :tags="tags"
      :documents="store.documents"
      :documents-error="store.documentsError"
      class="q-mb-sm"
      @change="store.setFilters"
      @reset="store.resetFilters"
    />

    <div class="collection-annotations__summary" aria-live="polite">
      <span data-testid="concordance-range">{{ rangeLabel }}</span>
      <q-spinner v-if="store.loading" color="primary" size="1.2em" aria-label="Loading annotations" />
      <template v-if="store.selected.size">
        <span class="collection-annotations__selected" data-testid="concordance-selected">
          {{ store.selected.size }} selected
        </span>
        <q-btn flat dense no-caps color="primary" label="Clear selection" @click="store.clearSelection" />
      </template>
      <q-space />
      <PagerButtons v-if="store.total > PAGE_SIZE" />
    </div>

    <div v-if="store.error" class="collection-annotations__state text-negative" role="alert" data-testid="concordance-error">
      {{ store.error }}
      <q-btn flat dense no-caps color="primary" label="Retry" @click="store.load" />
    </div>
    <div
      v-else-if="!store.loading && store.page && !store.rows.length"
      class="collection-annotations__state text-grey-8"
      data-testid="concordance-empty"
    >
      {{ emptyText }}
    </div>
    <div v-else-if="!store.page" class="collection-annotations__state text-grey-7">Loading annotations…</div>

    <ConcordanceTable
      v-if="store.rows.length && !store.error"
      ref="table"
      :rows="store.rows"
      :tags="tags"
      :selected="store.selected"
      :focused-id="store.focused?.id ?? null"
      :loading="store.loading"
      :class="{ 'collection-annotations__stale': store.loading }"
      @open="openContext"
      @toggle="store.toggleSelected"
      @select-page="store.setPageSelected"
    />

    <div v-if="store.total > PAGE_SIZE && store.rows.length" class="collection-annotations__summary q-mt-sm">
      <q-space />
      <PagerButtons />
    </div>

    <!-- Registered once a row is opened. -->
    <RightSidebarPanel v-if="store.focused" :id="CONTEXT_PANEL_ID" label="Document" icon="menu_book" :order="1">
      <ChunkContextPanel
        :target-chunk-id="chunkContext.target?.chunkId ?? null"
        :document="chunkContext.document"
        :chunks="chunkContext.chunks"
        :has-before="chunkContext.hasBefore"
        :has-after="chunkContext.hasAfter"
        :focus-request="chunkContext.focusRequest"
        :loading="chunkContext.loading"
        :extending="chunkContext.extending"
        :error="chunkContext.error"
        :highlight="highlight"
        target-name="Annotated passage"
        return-label="Focus on annotation"
        @extend="chunkContext.extend"
        @reload="chunkContext.load"
        @return="returnToRow"
      >
        <template #header>
          <div class="annotation-context" data-testid="annotation-context">
            <div class="annotation-context__meta text-caption">
              <span class="annotation-context__dot" :style="{ backgroundColor: focusedTag?.color ?? '#9e9e9e' }" aria-hidden="true" />
              <span>{{ focusedTag?.name ?? 'Unknown tag' }}</span>
              <span>·</span>
              <span>{{ statusText }}</span>
            </div>
            <blockquote class="annotation-context__text text-body2" data-testid="annotation-context-text">
              {{ store.focused.text ?? 'The annotated text is not available yet.' }}
            </blockquote>
            <q-btn
              v-if="store.focused.documentId"
              dense
              flat
              no-caps
              color="primary"
              icon="open_in_new"
              label="Open in document"
              class="annotation-context__open"
              :to="documentRoute"
            />
          </div>
        </template>
      </ChunkContextPanel>
    </RightSidebarPanel>
  </q-page>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, nextTick, reactive, ref, watch } from 'vue'
import { QBtn, QPage, QSpace, QSpinner, useQuasar } from 'quasar'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { SpanType, type AnnotationListRow } from 'src/generated/api'
import RightSidebarPanel from 'src/app/sidebar/RightSidebarPanel.vue'
import { useRightSidebarStore } from 'src/app/sidebar/rightSidebarStore'
import ChunkContextPanel from 'src/features/documents/ChunkContextPanel.vue'
import { useChunkContext } from 'src/features/documents/useChunkContext'
import { useTagsStore } from 'src/features/annotations/tagsStore'
import ConcordanceTable from './ConcordanceTable.vue'
import ConcordanceToolbar from './ConcordanceToolbar.vue'
import { PAGE_SIZE, defaultFilters, useConcordanceStore } from './concordanceStore'

const CONTEXT_PANEL_ID = 'annotation-context'

const route = useRoute()
const $q = useQuasar()
const store = reactive(useConcordanceStore())
const tagsStore = useTagsStore()
const { tags } = storeToRefs(tagsStore)
const rightSidebar = useRightSidebarStore()
const chunkContext = reactive(useChunkContext())
const table = ref<InstanceType<typeof ConcordanceTable> | null>(null)

const collectionId = computed(() => typeof route.params.collectionId === 'string' ? route.params.collectionId : '')

const rangeLabel = computed(() => {
  if (!store.page) return ''
  if (!store.total) return 'No matching annotations'
  const first = store.offset + 1
  const last = store.offset + store.rows.length
  return `Rows ${first}–${last} of ${store.total} matching annotations`
})

const emptyText = computed(() =>
  JSON.stringify(store.filters) === JSON.stringify(defaultFilters())
    ? 'This collection has no confirmed or proposed annotations yet.'
    : 'No annotations match these filters.')

// Previous/next page; rendered above and below the rows.
const PagerButtons = defineComponent(() => () => h('div', { class: 'row no-wrap q-gutter-x-xs' }, [
  h(QBtn, {
    dense: true,
    outline: true,
    noCaps: true,
    color: 'primary',
    icon: 'chevron_left',
    label: 'Previous',
    disable: store.offset === 0 || store.loading,
    onClick: () => store.goTo(store.offset - PAGE_SIZE)
  }),
  h(QBtn, {
    dense: true,
    outline: true,
    noCaps: true,
    color: 'primary',
    iconRight: 'chevron_right',
    label: 'Next',
    disable: store.offset + PAGE_SIZE >= store.total || store.loading,
    onClick: () => store.goTo(store.offset + PAGE_SIZE)
  })
]))

// ── Source context (shared right sidebar) ──
const highlight = computed(() => {
  const row = store.focused
  return row?.chunkId && row.start != null && row.end != null
    ? { chunkId: row.chunkId, start: row.start, end: row.end }
    : null
})

const focusedTag = computed(() => tags.value.find(t => t.id === store.focused?.tagId) ?? null)
const statusText = computed(() => ({
  [SpanType.pos]: 'Confirmed',
  [SpanType.auto]: 'Proposal',
  [SpanType.neg]: 'Rejected'
} as Record<string, string>)[store.focused?.type ?? ''] ?? 'Unknown status')

const documentRoute = computed(() => {
  const row = store.focused
  const order = chunkContext.chunks.find(c => c.id === row?.chunkId)?.order
  return {
    name: 'documentDetailV1',
    params: { collectionId: collectionId.value, documentId: row?.documentId ?? '' },
    query: {
      from: 'annotations',
      annotation: row?.id,
      chunk: row?.chunkId ?? undefined,
      order: order != null ? String(order) : undefined
    }
  }
})

function showContext (row: AnnotationListRow) {
  if (!row.documentId || !row.chunkId) return null
  return chunkContext.open({ documentId: row.documentId, chunkId: row.chunkId })
}

/** Opens the row in the sidebar; viewing context never changes the selection. */
async function openContext (row: AnnotationListRow) {
  store.focused = row
  const opening = showContext(row)
  await nextTick() // the panel registers when the first row is opened
  rightSidebar.activate(CONTEXT_PANEL_ID)
  await opening
}

function returnToRow () {
  const row = store.focused
  if (!row) return
  // On narrow screens the sidebar covers the list.
  if ($q.screen.lt.md) rightSidebar.open = false
  if (store.rows.some(r => r.id === row.id)) table.value?.reveal(row.id)
  else $q.notify({ type: 'info', message: 'This annotation is not on the current page.' })
}

// ── Workspace state across navigation ──
onBeforeRouteLeave(() => {
  store.scrollY = window.scrollY
})

watch(collectionId, async (id) => {
  if (!id) return
  chunkContext.clear()
  const returning = store.collectionId === id && !!store.page
  void tagsStore.fetchTagsByCollection(id)
  const loading = store.open(id)
  if (returning) {
    // Back from a document: the same place, then the rows as they are now.
    await nextTick()
    window.scrollTo(0, store.scrollY)
    if (store.focused) void showContext(store.focused)
  }
  await loading
}, { immediate: true })
</script>

<style scoped>
.collection-annotations__summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 12px;
  min-height: 36px;
  font-size: 0.85rem;
  color: rgba(0, 0, 0, 0.72);
}

.collection-annotations__selected {
  font-weight: 600;
  color: var(--q-primary);
}

.collection-annotations__state {
  padding: 24px 0;
}

.collection-annotations__stale {
  opacity: 0.55;
  transition: opacity 0.2s;
}

.annotation-context {
  margin-top: 6px;
}

.annotation-context__meta {
  display: flex;
  align-items: center;
  gap: 6px;
  color: rgba(0, 0, 0, 0.7);
}

.annotation-context__dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

.annotation-context__text {
  margin: 4px 0;
  padding: 4px 8px;
  border-left: 3px solid #ffd54f;
  background: #fffbe6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 9em;
  overflow-y: auto;
}

.annotation-context__open {
  margin-left: -6px;
}
</style>
