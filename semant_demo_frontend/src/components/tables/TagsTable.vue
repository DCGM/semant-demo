<template>
  <q-table
    flat
    :columns="columns"
    :rows="tags"
    row-key="id"
    :filter="filter"
    :pagination="initialPagination"
    :visible-columns="visibleColumns"
    square
    table-header-style="background-color: rgba(0, 0, 0, 0.04)"
    style="border-bottom: 1px solid rgba(0, 0, 0, 0.25)"
    :loading="loading"
  >
    <template #top>
      <div class="text-h5 text-weight-medium">
        Tags ({{ tags.length }} {{ tags.length === 1 ? 'item' : 'items' }})
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

      <div style="width: 100%" class="row items-center q-my-sm">
        <RefreshButton @click="handleRefresh" />
        <CreateButton @click="handleCreate" />
        <q-input
          class="q-ml-md"
          v-model="filter"
          placeholder="Search"
          dense
          debounce="300"
          outlined
          clearable
        >
          <template #prepend>
            <q-icon name="search" />
          </template>
        </q-input>
      </div>
    </template>

    <template #body-cell-actions="props">
      <q-td :props="props" class="q-pa-xs">
        <div class="row no-wrap items-center q-gutter-xs" @click.stop>
          <q-btn
            dense
            flat
            round
            color="primary"
            icon="edit"
            aria-label="Edit tag"
            @click="handleEdit(props.row)"
          >
            <q-tooltip>Edit tag</q-tooltip>
          </q-btn>
          <q-btn
            dense
            flat
            round
            color="negative"
            icon="delete"
            aria-label="Remove tag from collection"
            @click="handleDelete(props.row)"
          >
            <q-tooltip>Delete tag</q-tooltip>
          </q-btn>
        </div>
      </q-td>
    </template>

    <template #body-cell-color="props">
      <q-td :props="props">
        <div
          :key="props.row.color"
          class="color-swatch"
          :style="{ backgroundColor: props.row.color || 'transparent' }"
        >
          <q-tooltip>
            {{ props.row.color ? `Collection Color: ${props.row.color}` : 'No color set' }}
          </q-tooltip>
        </div>
      </q-td>
    </template>

    <template #body-cell-pictogram="props">
      <q-td :props="props">
        <div class="row items-center justify-center">
          <q-icon
            v-if="props.row.pictogram"
            :name="props.row.pictogram"
            size="22px"
          />
          <span v-else>-</span>
          <q-tooltip>
            {{
              props.row.pictogram
                ? `Pictogram: ${props.row.pictogram}`
                : 'No pictogram set'
            }}
          </q-tooltip>
        </div>
      </q-td>
    </template>

    <template #body-cell-examples="props">
      <q-td :props="props">
        <div v-if="props.row.examples?.length" class="tag-examples-list">
          <q-chip
            v-for="(example, index) in props.row.examples"
            :key="`${props.row.id}-${index}`"
            dense
            class="tag-example-chip"
          >
            {{ example }}
          </q-chip>
        </div>
        <span v-else>-</span>
      </q-td>
    </template>

    <template #body-cell-definition="props">
      <q-td :props="props" class="ellipsis">
        {{ props.row.definition || '-' }}
        <q-tooltip v-if="props.row.definition">
          {{ props.row.definition }}
        </q-tooltip>
      </q-td>
    </template>
  </q-table>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { QTableColumn, useQuasar } from 'quasar'
import { useRoute } from 'vue-router'

import useTagsDialog from 'src/composables/dialogs/useTagsDialog'
import useTags from 'src/composables/useTags'
import { PostTag, Tag } from 'src/models/tags'
import RefreshButton from '../custom/RefreshButton.vue'
import CreateButton from '../custom/CreateButton.vue'
import { PatchTag } from 'src/generated/api'

const route = useRoute()
const $q = useQuasar()
const { tags, loading, loadTags, createTag, deleteTag, updateTag } = useTags()
const { openTagsDialog } = useTagsDialog()
const filter = ref<string>('')
const initialPagination = {
  sortBy: 'tag_name',
  descending: false,
  page: 1,
  rowsPerPage: 12
}

const visibleColumns = ref<string[]>([
  'name',
  'shorthand',
  'color',
  'pictogram',
  'definition',
  'examples'
])

watch(visibleColumns, (newVal) => {
  console.log('Visible columns changed:', newVal)
})

const collectionId = computed<string>(() => {
  const value = route.params.collectionId
  if (typeof value !== 'string') {
    throw new Error('Missing required route param: collectionId')
  }
  return value
})

const handleRefresh = async () => {
  await loadTags(collectionId.value)
}

const handleCreate = () => {
  openTagsDialog({
    dialogType: 'CREATE'
  }).onOk(async (tagData: PostTag) => {
    await createTag(collectionId.value, tagData)
  })
}

const handleDelete = async (tag: Tag) => {
  $q.dialog({
    title: 'Delete Tag',
    html: true,
    message: `Are you sure you want to delete the tag <strong>${tag.name}</strong>?`,
    cancel: true,
    ok: {
      label: 'Delete',
      color: 'negative'
    },
    persistent: true
  }).onOk(async () => {
    await deleteTag(collectionId.value, tag.id)
  })
}

const handleEdit = (tag: Tag) => {
  openTagsDialog({
    dialogType: 'EDIT',
    tag
  }).onOk(async (updatedData: PatchTag) => {
    await updateTag(collectionId.value, tag.id, updatedData)
  })
}

onMounted(async () => {
  await loadTags(collectionId.value)
})

const columns: QTableColumn<Tag>[] = [
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
    name: 'name',
    label: 'Tag Name',
    field: (tag) => tag.name,
    align: 'left' as const,
    sortable: true,
    required: true
  },
  {
    name: 'shorthand',
    label: 'Shorthand',
    field: (tag) => tag.shorthand,
    align: 'left' as const,
    sortable: true
  },
  {
    name: 'color',
    label: 'Color',
    field: (tag) => tag.color,
    align: 'center' as const
  },
  {
    name: 'pictogram',
    label: 'Pictogram',
    field: (tag) => tag.pictogram,
    align: 'center' as const
  },
  {
    name: 'definition',
    label: 'Definition',
    field: (tag) => tag.definition,
    align: 'left' as const,
    sortable: true,
    style: 'max-width: 300px;'
  },
  {
    name: 'examples',
    label: 'Examples',
    field: (tag) => tag.examples?.join(', ') || '-',
    align: 'left' as const
  }
]

const columnOptions = columns.filter((column) => !column.required)
</script>

<style scoped>
.color-swatch {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  margin: 0 auto;
  border: 1px solid rgba(0, 0, 0, 0.2);
}

.tag-examples-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-example-chip {
  margin: 0;
  padding: 0 8px;
  min-height: 22px;
  border-radius: 999px;
  background: #ececec;
  border: 1px solid #d8d8d8;
  color: rgba(0, 0, 0, 0.72);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.1px;
}
</style>
