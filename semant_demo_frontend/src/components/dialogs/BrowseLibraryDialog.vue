<template>
  <q-dialog ref="dialogRef" @hide="onDialogHide" persistent>
    <q-card style="width: 1500px; max-width: 95vw">
      <q-card-section class="row items-center q-col-gutter-md">
        <div class="col-grow">
          <div class="text-h5">Browse Library</div>
          <div class="text-caption text-grey-7">
            Browse documents stored in the library and add them to the collection. Use the filters to narrow down the results.
          </div>
        </div>
        <div class="col-auto">
          <q-btn
            flat
            round
            dense
            icon="close"
            color="primary"
            aria-label="Close dialog"
            @click="onDialogCancel"
          />
        </div>
      </q-card-section>

      <q-separator />

      <q-card-section>
        <div class="row q-col-gutter-md">
          <div class="col-12 col-md-3">
            <q-input
              v-model="filters.title"
              outlined
              dense
              label="Title"
              clearable
              @keydown.enter="applyFilters"
            />
          </div>
          <div class="col-12 col-md-3">
            <q-input
              v-model="filters.author"
              outlined
              dense
              label="Author"
              clearable
              @keydown.enter="applyFilters"
            />
          </div>
          <div class="col-12 col-md-3">
            <q-input
              v-model="filters.publisher"
              outlined
              dense
              label="Publisher"
              clearable
              @keydown.enter="applyFilters"
            />
          </div>
          <div class="col-12 col-md-3">
            <q-input
              v-model="filters.documentType"
              outlined
              dense
              label="Document Type"
              clearable
              @keydown.enter="applyFilters"
            />
          </div>
        </div>

        <div class="row q-mt-md q-gutter-sm">
          <q-btn unelevated color="primary" label="Search" :loading="loading" @click="applyFilters" />
          <q-btn flat color="primary" label="Reset" :disable="loading" @click="resetFilters" />
        </div>
      </q-card-section>

      <q-separator />

      <q-card-section>
        <q-table
          flat
          dense
          :rows="rows"
          :columns="columns"
          row-key="id"
          v-model:pagination="pagination"
          :rows-per-page-options="[25, 50, 100]"
          :loading="loading"
          @request="onRequest"
          style="max-height: 55vh"
        >
          <template #no-data>
            <div class="full-width row flex-center text-grey-7 q-gutter-sm q-py-lg">
              <q-icon name="menu_book" size="1.2rem" />
              <span>No documents found for current filters.</span>
            </div>
          </template>
        </q-table>

        <div class="row items-center justify-between q-mt-md">
          <div class="text-caption text-grey-7">
            Showing {{ rows.length }} of {{ pagination.rowsNumber }} document{{ pagination.rowsNumber === 1 ? '' : 's' }}
          </div>
          <div class="text-caption text-grey-7">Use table pagination and column sorting.</div>
        </div>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useDialogPluginComponent, type QTableColumn, type QTableProps } from 'quasar'
import { Document, Documents } from 'src/models/documents'
import DocumentsRepository from 'src/repositories/DocumentsRepository'
import { onMounted, reactive, ref } from 'vue'
import { BrowseLibraryDialogProps } from './BrowseLibraryDialogTypes'

const props = defineProps<BrowseLibraryDialogProps>()
defineEmits([...useDialogPluginComponent.emits])

const { dialogRef, onDialogHide, onDialogCancel } = useDialogPluginComponent()

const PAGE_SIZE = 50

const filters = reactive({
  title: '',
  author: '',
  publisher: '',
  documentType: ''
})

const rows = ref<Documents>([])
const loading = ref(false)
const pagination = ref<NonNullable<QTableProps['pagination']>>({
  page: 1,
  rowsPerPage: PAGE_SIZE,
  rowsNumber: 0,
  sortBy: undefined,
  descending: false
})

const columns: QTableColumn<Document>[] = [
  {
    name: 'title',
    label: 'Title',
    field: (doc) => doc.title ?? '-',
    align: 'left',
    sortable: true
  },
  {
    name: 'author',
    label: 'Author',
    field: (doc) => doc.author?.join(', ') ?? '-',
    align: 'left'
  },
  {
    name: 'publisher',
    label: 'Publisher',
    field: (doc) => doc.publisher ?? '-',
    align: 'left'
  },
  {
    name: 'documentType',
    label: 'Type',
    field: (doc) => doc.documentType ?? '-',
    align: 'left'
  },
  {
    name: 'yearIssued',
    label: 'Year',
    field: (doc) => doc.yearIssued ?? '-',
    align: 'right',
    sortable: true
  }
]

const trimmed = (value: string): string | undefined => {
  const v = value.trim()
  return v.length > 0 ? v : undefined
}

const fetchPage = async (tablePagination: NonNullable<QTableProps['pagination']>) => {
  const page = tablePagination.page ?? 1
  const rowsPerPage = tablePagination.rowsPerPage && tablePagination.rowsPerPage > 0 ? tablePagination.rowsPerPage : PAGE_SIZE
  const offset = (page - 1) * rowsPerPage

  const response = await DocumentsRepository.browse({
    collectionId: props.collectionId,
    limit: rowsPerPage,
    offset,
    sortBy: typeof tablePagination.sortBy === 'string' ? tablePagination.sortBy : undefined,
    sortDesc: tablePagination.descending === true,
    title: trimmed(filters.title),
    author: trimmed(filters.author),
    publisher: trimmed(filters.publisher),
    documentType: trimmed(filters.documentType)
  })

  rows.value = response.items
  pagination.value = {
    ...tablePagination,
    rowsNumber: response.totalCount
  }
}

const applyFilters = async () => {
  pagination.value = {
    ...pagination.value,
    page: 1
  }

  loading.value = true
  try {
    await fetchPage(pagination.value)
  } finally {
    loading.value = false
  }
}

const onRequest = async (props: { pagination: NonNullable<QTableProps['pagination']> }) => {
  loading.value = true
  try {
    await fetchPage(props.pagination)
  } finally {
    loading.value = false
  }
}

const resetFilters = async () => {
  filters.title = ''
  filters.author = ''
  filters.publisher = ''
  filters.documentType = ''
  await applyFilters()
}

onMounted(async () => {
  await applyFilters()
})
</script>
