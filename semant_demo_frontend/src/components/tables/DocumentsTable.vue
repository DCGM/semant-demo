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
      <div class="text-h5 text-weight-medium">Documents ({{ documents.length }} {{ documents.length === 1 ? 'item' : 'items' }})</div>
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
    <template #body-cell-docStats="props">
      <q-td :props="props" @click.stop>
        <div v-if="statsLoading" class="doc-stats-cell doc-stats-cell--loading">
          <q-spinner size="14px" color="grey-5" />
        </div>
        <div v-else-if="documentStatsMap[props.row.id]" class="doc-stats-cell">
          <span class="doc-stat">
            <q-icon name="view_list" size="13px" />
            {{ documentStatsMap[props.row.id].chunksInCollection }}&thinsp;/&thinsp;{{ documentStatsMap[props.row.id].totalChunks }}
            <q-tooltip>
              <div class="doc-stat-tooltip">
                <strong>Chunks in collection</strong><br />
                {{ documentStatsMap[props.row.id].chunksInCollection }} out of {{ documentStatsMap[props.row.id].totalChunks }} total chunks of this document are added to the collection.
              </div>
            </q-tooltip>
          </span>
          <span class="doc-stat">
            <q-icon name="format_quote" size="13px" />
            {{ documentStatsMap[props.row.id].annotationsCount }}
            <q-tooltip>
              <div class="doc-stat-tooltip">
                <strong>Annotations</strong><br />
                {{ documentStatsMap[props.row.id].annotationsCount }} tag span{{ documentStatsMap[props.row.id].annotationsCount === 1 ? '' : 's' }} annotated in this document within this collection.
              </div>
            </q-tooltip>
          </span>
          <span class="doc-stat">
            <q-icon name="label" size="13px" />
            {{ documentStatsMap[props.row.id].distinctTagsCount }}
            <q-tooltip>
              <div class="doc-stat-tooltip">
                <strong>Distinct tags</strong><br />
                {{ documentStatsMap[props.row.id].distinctTagsCount }} unique tag{{ documentStatsMap[props.row.id].distinctTagsCount === 1 ? '' : 's' }} used in annotations across this document.
              </div>
            </q-tooltip>
          </span>
        </div>
        <span v-else class="text-grey-4">—</span>
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
          label="Remove selected"
          color="negative"
          size="md"
          @click="handleBulkRemoveFromCollection"
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
import { Document } from 'src/models/documents'
import useDocuments from 'src/composables/useDocuments'
import useBrowseLibraryDialog from 'src/composables/dialogs/useBrowseLibraryDialog'
import { computed, onMounted, ref } from 'vue'
import RefreshButton from '../custom/RefreshButton.vue'
import AddDocumentDropdownBtn from '../custom/AddDocumentDropdownBtn.vue'
import { QTableColumn, useQuasar } from 'quasar'
import { useRoute, useRouter } from 'vue-router'
import { useDocumentsRepository } from 'src/repositories/useDocumentsRepository'
import type { DocumentStats } from 'src/generated/api'

const { documents, loadDocumentsByCollection, removeDoc, removeManyDocs, loading } = useDocuments()
const { openBrowseLibraryDialog } = useBrowseLibraryDialog()
const documentsRepository = useDocumentsRepository()

const documentStatsMap = ref<Record<string, DocumentStats>>({})
const statsLoading = ref(false)

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

onMounted(async () => {
  await loadDocumentsByCollection(collectionId.value)
  void loadAllDocumentStats()
})

const loadAllDocumentStats = async () => {
  if (!documents.value.length) return
  statsLoading.value = true
  try {
    const results = await Promise.all(
      documents.value.map(doc =>
        documentsRepository.getStats(collectionId.value, doc.id).catch(() => null)
      )
    )
    const map: Record<string, DocumentStats> = {}
    for (const stats of results) {
      if (stats) map[stats.documentId] = stats
    }
    documentStatsMap.value = map
  } finally {
    statsLoading.value = false
  }
}

const handleRefresh = async () => {
  await loadDocumentsByCollection(collectionId.value)
  void loadAllDocumentStats()
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
    name: 'documentDetailV1',
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
  'docStats',
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
    name: 'docStats',
    label: 'Usage in collection',
    field: () => '',
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

.doc-stats-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  justify-content: center;
  white-space: nowrap;
}

.doc-stats-cell--loading {
  justify-content: center;
}

.doc-stat {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 0.78rem;
  color: #475569;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 2px 7px;
}

.doc-stat-tooltip {
  max-width: 220px;
  line-height: 1.5;
}
</style>
