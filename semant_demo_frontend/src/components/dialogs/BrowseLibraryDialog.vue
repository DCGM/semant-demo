<template>
  <q-dialog ref="dialogRef" @hide="onDialogHide">
    <q-card style="width: 1500px; max-width: 95vw">
      <q-card-section class="row items-center q-col-gutter-md">
        <div class="col-grow">
          <div class="text-h5">Browse Library</div>
          <div class="text-caption text-grey-7">
            Browse documents stored in the library and add them to the
            collection. Use the filters to narrow down the results.
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
          <q-btn
            unelevated
            color="primary"
            label="Search"
            :loading="loading"
            @click="applyFilters"
          />
          <q-btn
            flat
            color="primary"
            label="Reset"
            :disable="loading"
            @click="resetFilters"
          />
        </div>
      </q-card-section>

      <q-separator />

      <q-card-section>
        <q-table
          class="my-sticky-virtscroll-table"
          flat
          dense
          :rows="rows"
          :columns="columns"
          row-key="id"
          v-model:fullscreen="isTableFullscreen"
          v-model:pagination="pagination"
          :rows-per-page-options="[25, 50, 100]"
          :loading="loading"
          @request="onRequest"
          virtual-scroll
          :virtual-scroll-item-size="24"
          :virtual-scroll-sticky-size-start="48"
          :style="{ maxHeight: isTableFullscreen ? undefined : '60vh' }"
        >
          <template v-slot:top="props">
            <q-space />
            <q-btn
              flat
              round
              dense
              :icon="props.inFullscreen ? 'fullscreen_exit' : 'fullscreen'"
              @click="props.toggleFullscreen"
              class="q-ml-md"
            />
          </template>
          <template #body-cell-actions="tableProps">
            <q-td :props="tableProps" class="q-pa-xs">
              <div class="row items-center q-gutter-xs">
                <q-btn
                  dense
                  flat
                  round
                  :loading="addingDocumentIds.has(tableProps.row.id)"
                  :color="isDocumentInCollection(tableProps.row.id) ? 'positive' : 'primary'"
                  :icon="isDocumentInCollection(tableProps.row.id) ? 'check_circle' : 'add'"
                  :aria-label="
                    isDocumentInCollection(tableProps.row.id)
                      ? 'Document already in collection'
                      : 'Add document to current collection'
                  "
                  :disable="isDocumentInCollection(tableProps.row.id)"
                  @click="addDocumentToCurrentCollection(tableProps.row.id)"
                >
                  <q-tooltip v-if="isDocumentInCollection(tableProps.row.id)">
                    Already in collection
                  </q-tooltip>
                </q-btn>
              </div>
            </q-td>
          </template>
          <template #no-data>
            <div
              class="full-width row flex-center text-grey-7 q-gutter-sm q-py-lg"
            >
              <q-icon name="menu_book" size="1.2rem" />
              <span>No documents found for current filters.</span>
            </div>
          </template>
        </q-table>

        <div class="row items-center justify-between q-mt-md">
          <div class="text-caption text-grey-7">
            Showing {{ rows.length }} of {{ pagination.rowsNumber }} document{{
              pagination.rowsNumber === 1 ? '' : 's'
            }}
          </div>
          <div class="text-caption text-grey-7">
            Use table pagination and column sorting.
          </div>
        </div>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import {
  useDialogPluginComponent,
  type QTableColumn,
  type QTableProps
} from 'quasar'
import { Document } from 'src/models/documents'
import { useDocumentsRepository } from 'src/repositories/useDocumentsRepository'
import useDocuments from 'src/composables/useDocuments'
import {
  errorNotification
} from 'src/utils/notification'
import { computed, onMounted, reactive, ref } from 'vue'
import { BrowseLibraryDialogProps } from './BrowseLibraryDialogTypes'

defineEmits([...useDialogPluginComponent.emits])
const props = defineProps<BrowseLibraryDialogProps>()

const { dialogRef, onDialogHide, onDialogCancel } = useDialogPluginComponent()
const documentsRepository = useDocumentsRepository()
const { documents: collectionDocuments, loadDocumentsByCollection, addDoc } = useDocuments()

const PAGE_SIZE = 50

const filters = reactive({
  title: null as string | null,
  author: null as string | null,
  publisher: null as string | null,
  documentType: null as string | null
})

const loading = ref(false)
const isTableFullscreen = ref(false)
const rows = ref<Document[]>([])
const addingDocumentIds = ref(new Set<string>())
const collectionDocumentIds = computed(() => {
  return new Set(collectionDocuments.value.map((doc) => doc.id))
})
const pagination = ref<NonNullable<QTableProps['pagination']>>({
  page: 1,
  rowsPerPage: PAGE_SIZE,
  rowsNumber: 0,
  sortBy: undefined,
  descending: false
})

const columns: QTableColumn<Document>[] = [
  {
    name: 'actions',
    label: '',
    field: () => '',
    align: 'left'
  },
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

const trimmed = (value: string | null | undefined): string | undefined => {
  if (!value) {
    return undefined
  }

  const v = value.trim()
  return v.length > 0 ? v : undefined
}

const fetchPage = async (
  tablePagination: NonNullable<QTableProps['pagination']>
) => {
  const page = tablePagination.page ?? 1
  const rowsPerPage =
    tablePagination.rowsPerPage && tablePagination.rowsPerPage > 0
      ? tablePagination.rowsPerPage
      : PAGE_SIZE
  const offset = (page - 1) * rowsPerPage

  const response = await documentsRepository.browse({
    limit: rowsPerPage,
    offset,
    sortBy:
      typeof tablePagination.sortBy === 'string'
        ? tablePagination.sortBy
        : undefined,
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

const onRequest = async (props: {
  pagination: NonNullable<QTableProps['pagination']>
}) => {
  loading.value = true
  try {
    await fetchPage(props.pagination)
  } finally {
    loading.value = false
  }
}

const resetFilters = async () => {
  filters.title = null
  filters.author = null
  filters.publisher = null
  filters.documentType = null
  await applyFilters()
}

const isDocumentInCollection = (documentId: string): boolean => {
  return collectionDocumentIds.value.has(documentId)
}

const addDocumentToCurrentCollection = async (documentId: string) => {
  try {
    addingDocumentIds.value.add(documentId)
    const added = await addDoc(documentId, props.collectionId)
    if (added) {
      // Reload the collection documents
      await loadDocumentsByCollection(props.collectionId)
      return
    }
    errorNotification('Failed to add document to collection')
  } catch (error) {
    errorNotification('Failed to add document to collection')
  } finally {
    addingDocumentIds.value.delete(documentId)
  }
}

onMounted(async () => {
  await loadDocumentsByCollection(props.collectionId)
  await applyFilters()
})
</script>

<style lang="sass">
.my-sticky-virtscroll-table

  .q-table__top,
  .q-table__bottom,
  thead tr:first-child th /* bg color is important for th; just specify one */
    background-color: rgb(230, 230, 230)

  thead tr th
    position: sticky
    z-index: 1
  /* this will be the loading indicator */
  thead tr:last-child th
    /* height of all previous header rows */
    top: 48px
  thead tr:first-child th
    top: 0

  /* prevent scrolling behind sticky top row on focus */
  tbody
    /* height of all previous header rows */
    scroll-margin-top: 48px
</style>
