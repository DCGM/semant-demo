<template>
  <q-table
    flat square
    :columns="columns"
    :rows="documents"
    row-key="id"
    selection="multiple"
    v-model:selected="selectedDocs"
    :filter="filter"
    :pagination="initialPagination"
    :loading="loading"
    table-header-style="background-color: rgba(0,0,0,0.04)"
    style="border-bottom: 1px solid rgba(0,0,0,0.25)"
    :row-class="() => 'cursor-pointer'"
    @row-click="(_evt, row) => handleTagDocument(row.id)"
  >
    <template #top>
      <div class="text-h8 text-weight-medium">
        Documents ({{ documents.length }} {{ documents.length === 1 ? 'item' : 'items' }})
      </div>
      <q-space />
      <q-input v-model="filter" placeholder="Search" dense debounce="300" outlined clearable class="q-ml-md">
        <template #prepend><q-icon name="search" /></template>
      </q-input>
    </template>
  </q-table>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { QTableColumn } from 'quasar'
import { useRoute, useRouter } from 'vue-router'
import { Document } from 'src/models/documents'
import useDocuments from 'src/composables/useDocuments'

const props = defineProps<{
  modelValue?: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [ids: string[]]
}>()

const { documents, loadDocumentsByCollection, loading } = useDocuments()
const $route = useRoute()
const $router = useRouter()

const collectionId = computed<string>(() => {
  const value = $route.params.collectionId
  if (typeof value !== 'string') throw new Error('Missing required route param: collectionId')
  return value
})

const filter = ref('')
const initialPagination = { sortBy: 'documentTitle', descending: false, page: 1, rowsPerPage: 12 }

const selectedDocs = computed({
  get: () => documents.value.filter((d) => props.modelValue?.includes(d.id)),
  set: (docs: Document[]) => emit('update:modelValue', docs.map((d) => d.id))
})

onMounted(() => loadDocumentsByCollection(collectionId.value))

const handleTagDocument = (documentId: string) => {
  $router.push({ name: 'documentDetailV1', params: { collectionId: collectionId.value, documentId } })
}

const columns: QTableColumn<Document>[] = [
  { name: 'documentTitle', label: 'Document Title', field: (d) => d.title, align: 'left', sortable: true },
  { name: 'author', label: 'Author', field: (d) => d.author?.join(', ') ?? '-', align: 'center' },
  { name: 'yearIssued', label: 'Year', field: (d) => d.yearIssued ?? '-', align: 'center', sortable: true },
  { name: 'language', label: 'Language', field: (d) => d.language ?? '-', align: 'center' }
]
</script>
