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
      <q-select
        v-model="visibleColumns"
        multiple
        outlined
        options-dense
        dense
        :display-value="$q.lang.table.columns"
        :options="columnOptions"
        option-value="name"
        emit-value
        style="min-width: 150px"
        transition-hide="scale"
        transition-show="scale"
        color="primary"
        class="text-grey-2"
      >
        <template #option="{ itemProps, opt, selected, toggleOption }">
          <q-item v-bind="itemProps">
            <q-item-section>
              <q-item-label>{{ opt.label }}</q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-toggle
                :model-value="selected"
                @update:model-value="toggleOption(opt)"
              />
            </q-item-section>
          </q-item>
        </template>
      </q-select>
    </template>
    <template #body-cell-actions="tableProps">
      <q-td :props="tableProps">
        <div class="row no-wrap items-center q-gutter-xs" @click.stop>
          <q-btn
            flat
            dense
            round
            icon="open_in_new"
            color="primary"
            @click="emit('enter', tableProps.row.id)"
          />
          <q-btn
            flat
            dense
            round
            icon="edit"
            color="primary"
            @click="emit('edit', tableProps.row)"
          />
          <q-btn
            flat
            dense
            round
            icon="delete"
            color="negative"
            @click="emit('delete', tableProps.row)"
          />
        </div>
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
          icon="delete_sweep"
          label="Delete selected"
          color="negative"
          size="md"
          @click="handleBulkDelete"
        />
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
import { computed, ref } from 'vue'
import { useQuasar, type QTableColumn } from 'quasar'
import { Collection } from 'src/models/collections'

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
}>()

const $q = useQuasar()
const selected = ref<Collection[]>([])

const initialPagination = {
  sortBy: 'collectionName',
  descending: false,
  page: 1,
  rowsPerPage: 12
}

const columns: QTableColumn<Collection>[] = [
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

const visibleColumns = ref<string[]>(['collectionName', 'description', 'owner', 'updatedAt', 'color', 'createdAt'])
const columnOptions = columns.filter((column) => !column.required)

const handleBulkDelete = () => {
  if (selected.value.length === 0) return
  const count = selected.value.length
  $q.dialog({
    title: 'Delete Selected Collections',
    html: true,
    message: `Are you sure you want to delete <strong>${count}</strong> selected collection${count === 1 ? '' : 's'}?`,
    cancel: true,
    ok: {
      label: 'Delete selected',
      color: 'negative'
    },
    persistent: true
  }).onOk(() => {
    emit('deleteMany', selected.value.map(c => c.id))
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
