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
      <q-td :props="tableProps" class="text-center">
        <div
          class="color-swatch"
          :style="{ backgroundColor: tableProps.row.color || 'transparent' }"
        />
      </q-td>
    </template>
  </q-table>
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
}>()

const $q = useQuasar()

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
    field: (row) => row.name,
    align: 'left',
    sortable: true,
    required: true
  },
  {
    name: 'color',
    label: 'Color',
    field: (row) => row.color,
    align: 'center'
  },
  {
    name: 'description',
    label: 'Description',
    field: (row) => row.description ?? '-',
    align: 'left'
  },
  {
    name: 'owner',
    label: 'Owner',
    field: (row) => row.userId,
    align: 'left'
  },
  {
    name: 'createdAt',
    label: 'Created',
    field: (row) => row.createdAt.toLocaleDateString(),
    align: 'left',
    sortable: true
  },
  {
    name: 'updatedAt',
    label: 'Updated',
    field: (row) => row.updatedAt.toLocaleDateString(),
    align: 'left',
    sortable: true
  }
]

const visibleColumns = ref<string[]>(['collectionName', 'description', 'owner', 'updatedAt', 'color', 'createdAt'])
const columnOptions = columns.filter((column) => !column.required)

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
</style>
