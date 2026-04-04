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
    :row-class="() => 'cursor-pointer'"
    @row-click="(_evt, row) => handleTagDocument(row.id)"
    :loading="loading"
  >
    <template #top>
      <div class="text-h5 text-weight-medium">Documents ({{ documents.length }} items)</div>
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
        <AddDocumentDropdownBtn
          @browse-library="handleBrowseLibrary"
          @create-document="handleCreateDocument"
          @upload-document="handleUploadDocument"
        />
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
            icon="border_color"
            aria-label="Tag document"
            @click="handleTagDocument(props.row.id)"
          >
            <q-tooltip>Tag document</q-tooltip>
          </q-btn>
          <q-btn
            dense
            flat
            round
            color="negative"
            icon="cancel"
            aria-label="Remove document from collection"
            @click="handleRemoveFromCollection(props.row)"
          >
            <q-tooltip>Remove from collection</q-tooltip>
          </q-btn>
        </div>
      </q-td>
    </template>
  </q-table>

  <transition name="fade-slide-up">
    <q-page-sticky
      v-if="selected.length > 0"
      position="bottom"
      :offset="[0, 30]"
    >
      <q-card class="bulk-actions-card q-px-md q-py-sm">
        <div class="row items-center q-gutter-md">
          <div class="text-body1 text-weight-medium">
            Selected: {{ selected.length }}
          </div>
          <q-space />
          <q-btn
            color="negative"
            icon="delete_sweep"
            label="Remove Selected"
            @click="handleBulkRemoveFromCollection"
          />
        </div>
      </q-card>
    </q-page-sticky>
  </transition>
</template>

<script setup lang="ts">
import { Document } from 'src/models/documents'
import useDocuments from 'src/composables/useDocuments'
import useBrowseLibraryDialog from 'src/composables/dialogs/useBrowseLibraryDialog'
import { computed, onMounted, ref } from 'vue'
import RefreshButton from '../custom/RefreshButton.vue'
import AddDocumentDropdownBtn from '../custom/AddDocumentDropdownBtn.vue'
import { QTableColumn, useQuasar } from 'quasar'
import { useRoute, useRouter } from 'vue-router'

const { documents, loadDocuments, removeDoc, removeManyDocs, loading } = useDocuments()
const { openBrowseLibraryDialog } = useBrowseLibraryDialog()

const $q = useQuasar()
const $route = useRoute()
const $router = useRouter()
const collectionId = computed<string>(() => {
  const value = $route.params.collectionId
  if (typeof value !== 'string') {
    throw new Error('Missing required route param: collectionId')
  }
  return value
})

onMounted(() => {
  loadDocuments(collectionId.value)
})

const handleRefresh = async () => {
  await loadDocuments(collectionId.value)
}

const handleBrowseLibrary = () => {
  openBrowseLibraryDialog({ collectionId: collectionId.value })
}

const handleCreateDocument = () => {
  console.log('Create document - not implemented yet')
}

const handleUploadDocument = () => {
  console.log('Upload document - not implemented yet')
}

const handleTagDocument = (documentId: string) => {
  $router.push({
    name: 'documentTagging',
    params: {
      collectionId: collectionId.value,
      documentId
    }
  })
}

const handleRemoveFromCollection = async (document: Document) => {
  $q.dialog({
    title: 'Remove Document',
    html: true,
    message: `Are you sure you want to remove document <strong>${document.title}</strong> from the collection?`,
    cancel: true,
    ok: {
      label: 'Delete',
      color: 'negative'
    },
    persistent: true
  }).onOk(async () => {
    await removeDoc(document.id, collectionId.value)
  })
}

const handleBulkRemoveFromCollection = () => {
  if (selected.value.length === 0) {
    return
  }

  const selectedIds = selected.value.map((doc) => doc.id)
  const count = selectedIds.length

  $q.dialog({
    title: 'Remove Selected Documents',
    html: true,
    message: `Are you sure you want to remove <strong>${count}</strong> selected document${count === 1 ? '' : 's'} from the collection?`,
    cancel: true,
    ok: {
      label: 'Delete selected',
      color: 'negative'
    },
    persistent: true
  }).onOk(async () => {
    await removeManyDocs(selectedIds, collectionId.value)
    selected.value = []
  })
}

const selected = ref<Document[]>([])
const filter = ref<string>('')
const initialPagination = {
  sortBy: 'documentTitle',
  descending: false,
  page: 1,
  rowsPerPage: 12
}
const visibleColumns = ref<string[]>([
  'actions',
  'documentTitle',
  'author',
  'yearIssued',
  'language',
  'publisher',
  'placeOfPublication'
])

const columns: QTableColumn<Document>[] = [
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

<style scoped>
.bulk-actions-card {
  min-width: 360px;
  width: min(92vw, 550px);
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 12px;
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.16);
  backdrop-filter: saturate(120%) blur(2px);
}

.fade-slide-up-enter-active,
.fade-slide-up-leave-active {
  transition: all 0.2s ease;
}

.fade-slide-up-enter-from,
.fade-slide-up-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>
