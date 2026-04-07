<template>
  <q-table
    flat
    :columns="columns"
    :rows="tags"
    row-key="tag_uuid"
    :filter="filter"
    :pagination="initialPagination"
    :visible-columns="visibleColumns"
    square
    table-header-style="background-color: rgba(0, 0, 0, 0.04)"
    style="border-bottom: 1px solid rgba(0, 0, 0, 0.25)"
    :loading="loading"
  >
    <template #top>
      <div class="text-h5 text-weight-medium">Tags ({{ tags.length }} {{ tags.length === 1 ? 'item' : 'items' }})</div>
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
        <RefreshButton @click="$emit('refresh')" />
        <CreateButton @click="$emit('create')" />
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

    <template #body-cell-tag_color="props">
      <q-td :props="props">
        <div class="row items-center q-gutter-sm">
          <span class="tag-color-dot" :style="{ backgroundColor: props.row.tagColor || '#BDBDBD' }" />
          <span>{{ props.row.tagColor || '-' }}</span>
        </div>
      </q-td>
    </template>

    <template #body-cell-tag_pictogram="props">
      <q-td :props="props">
        <div class="row items-center q-gutter-sm">
          <q-icon v-if="props.row.tagPictogram" :name="props.row.tagPictogram" />
          <span>{{ props.row.tagPictogram || '-' }}</span>
        </div>
      </q-td>
    </template>

    <template #body-cell-tag_examples="props">
      <q-td :props="props">
        <div v-if="props.row.tagExamples?.length" class="row q-gutter-xs">
          <q-chip
            v-for="(example, index) in props.row.tagExamples"
            :key="`${props.row.tagUuid}-${index}`"
            dense
            square
            color="grey-2"
            text-color="dark"
            class="q-ma-none"
          >
            {{ example }}
          </q-chip>
        </div>
        <span v-else>-</span>
      </q-td>
    </template>

    <template #body-cell-tag_definition="props">
      <q-td :props="props" class="tag-definition-cell">
        {{ props.row.tagDefinition || '-' }}
      </q-td>
    </template>
  </q-table>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { QTableColumn, useQuasar } from 'quasar'

import { Tag, Tags } from 'src/models/tags'
import RefreshButton from '../custom/RefreshButton.vue'
import CreateButton from '../custom/CreateButton.vue'

defineEmits<{
  refresh: []
  create: []
}>()

const props = defineProps<{
  tags: Tags
  loading: boolean
}>()

const $q = useQuasar()
const filter = ref<string>('')
const initialPagination = {
  sortBy: 'tag_name',
  descending: false,
  page: 1,
  rowsPerPage: 12
}

const visibleColumns = ref<string[]>([
  'tagName',
  'tagShorthand',
  'tagColor',
  'tagPictogram',
  'tagDefinition',
  'tagExamples'
])

const columns: QTableColumn<Tag>[] = [
  {
    name: 'tagName',
    label: 'Tag Name',
    field: (tag) => tag.tagName,
    align: 'left' as const,
    sortable: true,
    required: true
  },
  {
    name: 'tagShorthand',
    label: 'Shorthand',
    field: (tag) => tag.tagShorthand,
    align: 'left' as const,
    sortable: true
  },
  {
    name: 'tagColor',
    label: 'Color',
    field: (tag) => tag.tagColor,
    align: 'left' as const,
    sortable: true
  },
  {
    name: 'tagPictogram',
    label: 'Pictogram',
    field: (tag) => tag.tagPictogram,
    align: 'left' as const,
    sortable: true
  },
  {
    name: 'tagDefinition',
    label: 'Definition',
    field: (tag) => tag.tagDefinition,
    align: 'left' as const,
    sortable: true,
    style: 'max-width: 300px; white-space: normal;'
  },
  {
    name: 'tagExamples',
    label: 'Examples',
    field: (tag) => tag.tagExamples?.join(', ') || '-',
    align: 'left' as const,
    sortable: false
  },
  {
    name: 'tagUuid',
    label: 'Tag UUID',
    field: (tag) => tag.tagUuid,
    align: 'left' as const,
    sortable: true
  }
]

const columnOptions = computed(() =>
  columns
    .filter((column) => column.name !== 'tagName')
    .map((column) => ({
      name: column.name,
      label: column.label,
      value: column.name
    }))
)

const tags = computed(() => props.tags)
const loading = computed(() => props.loading)
</script>

<style scoped lang="scss">
.tag-color-dot {
  width: 12px;
  height: 12px;
  border-radius: 999px;
  border: 1px solid rgba(0, 0, 0, 0.25);
  display: inline-block;
}

.tag-definition-cell {
  line-height: 1.35;
}
</style>
