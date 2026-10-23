<template>
  <q-table
    class="q-mt-sm"
    flat
    square
    :rows="collections"
    :filter="filter"
    :columns="columns"
    :visible-columns="visibleColumns"
    row-key="id"
    selection="multiple"
    v-model:selected="selected"
    :row-class="() => 'cursor-pointer'"
    @row-click="handleRowClick"
    style="border-bottom: 1px solid rgba(0, 0, 0, 0.25)"
    table-header-style="background-color: rgba(0, 0, 0, 0.04)"
    :pagination="initialPagination"
    :loading="loading"
  >
    <template #top>
      <div class="text-h5 text-weight-medium">
        Collections ({{ collections.length }} {{ collections.length === 1 ? 'item' : 'items' }})
      </div>
      <q-space />
      <ColumnPicker v-model="visibleColumns" :columns="columns" />
    </template>
    <!-- Every column but Actions can be resized by dragging the right edge of its header. -->
    <template #header-cell="tableProps">
      <q-th :props="tableProps" class="resizable-th">
        {{ tableProps.col.label }}
        <span
          v-if="tableProps.col.name !== 'actions'"
          class="col-resizer"
          role="separator"
          aria-orientation="vertical"
          :aria-label="`Resize the ${tableProps.col.label} column`"
          title="Drag to resize, double-click to reset"
          @pointerdown.stop.prevent="startResize($event, tableProps.col.name)"
          @click.stop
          @dblclick.stop="resetWidth(tableProps.col.name)"
        />
      </q-th>
    </template>
    <template #body-cell-actions="tableProps">
      <q-td :props="tableProps">
        <div v-if="isOwned(tableProps.row)" class="row no-wrap items-center q-gutter-xs" @click.stop>
          <q-btn
            flat
            dense
            round
            icon="share"
            color="primary"
            aria-label="Share collection"
            @click="emit('share', tableProps.row)"
          >
            <q-tooltip>Share collection</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            round
            icon="edit"
            color="primary"
            aria-label="Edit collection"
            @click="emit('edit', tableProps.row)"
          />
          <q-btn
            flat
            dense
            round
            icon="delete"
            color="negative"
            aria-label="Delete collection"
            @click="emit('delete', tableProps.row)"
          />
        </div>
        <q-icon v-else name="group" color="grey-6" size="sm" @click.stop>
          <q-tooltip>Shared with you by {{ tableProps.row.owner }}; only the owner can share, edit or delete it.</q-tooltip>
        </q-icon>
      </q-td>
    </template>
    <template #body-cell-color="tableProps">
      <q-td :props="tableProps">
        <div
          class="color-swatch"
          :style="{ backgroundColor: tableProps.row.color || 'transparent' }"
        >
          <q-tooltip>
            {{ tableProps.row.color ? `Collection Color: ${tableProps.row.color}` : 'No color set' }}
          </q-tooltip>
        </div>
      </q-td>
    </template>
    <template #body-cell-description="props">
      <q-td :props="props" class="ellipsis">
        {{ props.row.description || '-' }}
        <q-tooltip v-if="props.row.description">
          {{ props.row.description }}
        </q-tooltip>
      </q-td>
    </template>
  </q-table>

  <Teleport to="body">
    <transition name="fade-slide-up">
      <div v-if="selected.length > 0" class="bulk-action-bar">
        <span class="bulk-count">{{ selected.length }} selected</span>
        <q-btn
          flat dense no-caps
          icon="share"
          label="Share selected"
          color="primary"
          size="md"
          :disable="!allSelectedOwned"
          @click="handleBulkShare"
        />
        <q-btn
          flat dense no-caps
          icon="delete_sweep"
          label="Delete selected"
          color="negative"
          size="md"
          :disable="!allSelectedOwned"
          @click="handleBulkDelete"
        />
        <span v-if="!allSelectedOwned" class="bulk-hint">Only the owner can share or delete a collection.</span>
        <q-btn
          flat dense round
          icon="close"
          size="md"
          color="grey-4"
          title="Clear selection"
          @click="selected = []"
        />
      </div>
    </transition>
  </Teleport>
</template>

<script setup lang="ts">
import ColumnPicker from 'src/shared/ui/ColumnPicker.vue'
import { computed, ref, watch } from 'vue'
import type { QTableColumn } from 'quasar'
import { Collection, UserSearchResult } from 'src/generated/api'
import useShareCollectionsDialog from './useShareCollectionsDialog'
import { collectionRights } from './permissions'
import useConfirmDelete from 'src/shared/useConfirmDelete'
import { plural } from 'src/shared/plural'
import { annotationsOfCollections } from 'src/features/annotations/annotationCounts'
import { useResizableColumns } from 'src/shared/useResizableColumns'

interface Props {
  collections: Collection[]
  filter?: string
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  filter: '',
  loading: false
})

const emit = defineEmits<
  {(event: 'enter', collectionId: string): void
  (event: 'edit', collection: Collection): void
  (event: 'delete', collection: Collection): void
  (event: 'deleteMany', collectionIds: string[]): void
  (event: 'share', collection: Collection): void
  (event: 'shareMany', payload: { collectionIds: string[]; userId: string }): void
}>()

const confirmDelete = useConfirmDelete()
const selected = ref<Collection[]>([])
const { openShareCollectionsDialog } = useShareCollectionsDialog()

const initialPagination = {
  sortBy: 'collectionName',
  descending: false,
  page: 1,
  rowsPerPage: 12
}

const baseColumns: QTableColumn<Collection>[] = [
  {
    name: 'actions',
    label: 'Actions',
    field: () => '',
    align: 'center' as const,
    required: true,
    headerStyle: 'width: 1%; white-space: nowrap;',
    style: 'width: 1%; white-space: nowrap;'
  },
  {
    name: 'collectionName',
    label: 'Name',
    field: (row) => row.name || '-',
    align: 'left',
    sortable: true,
    required: true
  },
  {
    name: 'color',
    label: 'Color',
    field: (row) => row.color || '-',
    align: 'center'
  },
  {
    name: 'description',
    label: 'Description',
    field: (row) => row.description || '-',
    align: 'left',
    style: 'max-width: 300px;'
  },
  {
    name: 'owner',
    label: 'Owner',
    field: (row) => row.owner || '-',
    align: 'left'
  },
  {
    name: 'createdAt',
    label: 'Created',
    field: (row) => row.createdAt ? row.createdAt.toLocaleDateString() : '-',
    align: 'left',
    sortable: true
  },
  {
    name: 'updatedAt',
    label: 'Updated',
    field: (row) => row.updatedAt ? row.updatedAt.toLocaleDateString() : '-',
    align: 'left',
    sortable: true
  }
]

const { columns, startResize, resetWidth } = useResizableColumns('collections', baseColumns)

const visibleColumns = ref<string[]>(['collectionName', 'description', 'owner', 'updatedAt', 'color', 'createdAt'])

// A selected collection the rows no longer show (filtered out, deleted) leaves the
// selection, so the bulk actions act only on what is shown.
watch(() => props.collections, (rows) => {
  const shown = new Set(rows.map((c) => c.id))
  if (selected.value.some((c) => !shown.has(c.id))) selected.value = selected.value.filter((c) => shown.has(c.id))
})

// Sharing and deleting are the owner's (ADR 0007).
const isOwned = (collection: Collection) => collectionRights(collection).share
const allSelectedOwned = computed(() => selected.value.every(isOwned))

const handleBulkShare = () => {
  if (selected.value.length === 0 || !allSelectedOwned.value) return
  const collectionIds = selected.value.map((c) => c.id)
  openShareCollectionsDialog({ collectionCount: collectionIds.length })
    .onOk((user: UserSearchResult) => {
      emit('shareMany', { collectionIds, userId: user.id })
      selected.value = []
    })
}

const handleBulkDelete = () => {
  if (selected.value.length === 0 || !allSelectedOwned.value) return
  const count = selected.value.length
  const ids = selected.value.map(c => c.id)
  confirmDelete({
    title: 'Delete Selected Collections',
    message: `Delete ${plural(count, 'selected collection')}?`,
    okLabel: 'Delete selected',
    alsoDeletes: annotationsOfCollections(ids)
  }).onOk(() => {
    emit('deleteMany', ids)
    selected.value = []
  })
}

const handleRowClick = (_evt: Event, row: Collection) => {
  emit('enter', row.id)
}

const collections = computed(() => props.collections)
const filter = computed(() => props.filter)
const loading = computed(() => props.loading)
</script>

<style scoped>
.resizable-th {
  position: relative;
}

/* The drag handle on the header's right edge; a line shows while hovered. */
.col-resizer {
  position: absolute;
  top: 0;
  right: 0;
  width: 8px;
  height: 100%;
  cursor: col-resize;
  touch-action: none;
}

.col-resizer::after {
  content: '';
  position: absolute;
  top: 25%;
  right: 3px;
  width: 2px;
  height: 50%;
  background: transparent;
  transition: background 0.15s;
}

.resizable-th:hover .col-resizer::after {
  background: rgba(0, 0, 0, 0.2);
}

.col-resizer:hover::after {
  background: #1976d2;
}

.color-swatch {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  margin: 0 auto;
  border: 1px solid rgba(0, 0, 0, 0.2);
}

.bulk-action-bar {
  position: fixed;
  bottom: 28px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  background: #1c2636;
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.28);
  z-index: 9000;
  white-space: nowrap;
}

.bulk-hint {
  font-size: 0.8rem;
  color: #cbd5e1;
  padding: 0 6px;
}

.bulk-count {
  font-size: 0.92rem;
  font-weight: 600;
  padding: 0 10px;
  color: #f1f5f9;
}

.fade-slide-up-enter-active,
.fade-slide-up-leave-active {
  transition: all 0.2s ease;
}

.fade-slide-up-enter-from,
.fade-slide-up-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(10px);
}
</style>
