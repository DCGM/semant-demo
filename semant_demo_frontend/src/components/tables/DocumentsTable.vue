<template>
  <q-table
    flat
    :columns="columns"
    :rows="documents"
    row-key="id"
    selection="multiple"
    v-model:selected="selected"
    :filter="filter"
    :pagination="initialPagination"
    :visible-columns="visibleColumns"
    square
    table-header-style="background-color: rgba(0, 0, 0, 0.04)"
    style="border-bottom: 1px solid rgba(0, 0, 0, 0.25)"
  >
    <template #top>
      <div class="text-h5 text-weight-medium">Project Documents</div>
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
      <div style="width: 100%" class="q-mt-sm">
        <RefreshButton @click="handleRefresh" />
        <AddDocumentDropdownBtn
          @browse-library="handleBrowseLibrary"
          @create-document="handleCreateDocument"
          @upload-document="handleUploadDocument"
        />
      </div>
    </template>
  </q-table>
</template>

<script setup lang="ts">
import { Document } from 'src/models/documents'
import useDocuments from 'src/composables/useDocuments'
import useBrowseLibraryDialog from 'src/composables/dialogs/useBrowseLibraryDialog'
import { computed, onMounted, ref } from 'vue'
import RefreshButton from '../custom/RefreshButton.vue'
import AddDocumentDropdownBtn from '../custom/AddDocumentDropdownBtn.vue'
import { QTableColumn } from 'quasar'
import { useRoute } from 'vue-router'

const { documents, loadDocuments } = useDocuments()
const { openBrowseLibraryDialog } = useBrowseLibraryDialog()

const route = useRoute()
const collectionId = computed(() => {
  const value = route.params.collectionId
  return typeof value === 'string' ? value : undefined
})

onMounted(() => {
  loadDocuments(collectionId.value)
})

const handleRefresh = async () => {
  await loadDocuments(collectionId.value)
}

const handleBrowseLibrary = () => {
  openBrowseLibraryDialog({ collectionId: collectionId.value }).onDismiss(() => {
    loadDocuments(collectionId.value)
  })
}

const handleCreateDocument = () => {
  console.log('Create document - not implemented yet')
}

const handleUploadDocument = () => {
  console.log('Upload document - not implemented yet')
}

const selected = ref<number[]>([])
const filter = ref<string>('')
const initialPagination = {
  sortBy: 'documentTitle',
  descending: false,
  page: 1,
  rowsPerPage: 12
}
const visibleColumns = ref<string[]>([
  'documentTitle',
  'author',
  'documentType',
  'yearIssued',
  'language',
  'publisher',
  'placeOfPublication'
])

const columns: QTableColumn<Document>[] = [
  {
    name: 'documentTitle',
    label: 'Document Title',
    field: (doc) => doc.title,
    align: 'left' as const,
    sortable: true,
    required: true
  },
  {
    name: 'author',
    label: 'Author',
    field: (doc) => doc.author?.join(', ') ?? '-',
    align: 'center' as const
  },
  {
    name: 'dateIssued',
    label: 'Date Issued',
    field: (doc) => doc.dateIssued ?? '-',
    align: 'center' as const,
    sortable: true
  },
  {
    name: 'yearIssued',
    label: 'Year Issued',
    field: (doc) => doc.yearIssued ?? '-',
    align: 'center' as const,
    sortable: true
  },
  {
    name: 'language',
    label: 'Language',
    field: (doc) => doc.language ?? '-',
    align: 'center' as const
  },
  {
    name: 'publisher',
    label: 'Publisher',
    field: (doc) => doc.publisher ?? '-',
    align: 'center' as const
  },
  {
    name: 'placeOfPublication',
    label: 'Place of Publication',
    field: (doc) => doc.placeOfPublication ?? '-',
    align: 'center' as const
  },
  {
    name: 'documentType',
    label: 'Document Type',
    field: (doc) => doc.documentType ?? '-',
    align: 'center' as const
  },
  {
    name: 'keywords',
    label: 'Keywords',
    field: (doc) => doc.keywords?.join(', ') ?? '-',
    align: 'center' as const
  }
]

const columnOptions = columns.filter((col) => !col.required)
</script>
