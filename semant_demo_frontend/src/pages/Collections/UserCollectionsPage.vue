<template>
  <q-page class="q-pt-md" p>
    <PageTitle title="Collections" />
    <div class="row items-center q-my-sm q-px-md">
      <RefreshButton @click="handleRefresh" />
      <CreateButton @click="handleCreate" />

      <q-input
        v-model="searchQuery"
        outlined
        dense
        placeholder="Search collections..."
        class="q-mx-md"
        style="max-width: 300px"
        clearable
        @clear="searchQuery = ''"
      >
        <template #prepend>
          <q-icon name="search" />
        </template>
      </q-input>

      <q-space />

      <q-btn-toggle
        v-model="viewMode"
        class="q-mr-md"
        unelevated
        toggle-color="primary"
        color="grey-3"
        text-color="grey-8"
        :options="[
          { value: 'tiles', icon: 'grid_view', label: 'Tiles' },
          { value: 'table', icon: 'table_rows', label: 'Table' }
        ]"
      />

      <q-pagination
        class="q-mr-md gt-sm"
        v-model="currentPage"
        :max="pageCount"
        color="primary"
        boundary-numbers
        boundary-links
        direction-links
        gutter="10px"
      />
    </div>
    <div v-if="viewMode === 'tiles'" class="row q-col-gutter-md q-px-lg q-py-md">
      <CreateCollectionCard @click="handleCreate"/>

      <CollectionCard
        v-for="(collection, index) in paginatedItems"
        :key="collection.id ?? index"
        :collection="collection"
        @enter="handleEnter"
        @edit="handleEdit"
        @delete="handleDelete"
      />
    </div>
    <CollectionsTable
      v-else
      :collections="collections"
      :filter="searchQuery"
      :loading="loading"
      @enter="handleEnter"
      @edit="handleEdit"
      @delete="handleDelete"
    />
    <div class="row justify-center q-mt-md lt-md">
      <q-pagination
        v-model="currentPage"
        :max="pageCount"
        color="primary"
        boundary-numbers
        direction-links
        gutter="10px"
        boundary-links
      />
    </div>
    <ErrorDisplay :error="error" />
    <q-inner-loading :showing="loading"></q-inner-loading>
  </q-page>
</template>

<script setup lang="ts">
import PageTitle from 'src/components/custom/PageTitle.vue'
import RefreshButton from 'src/components/custom/RefreshButton.vue'
import CreateCollectionCard from 'src/components/custom/CreateCollectionCard.vue'
import CollectionsTable from 'src/components/tables/CollectionsTable.vue'

import usePagination from 'src/composables/usePagination'
import useCollections from 'src/composables/useCollections'
import useCollectionDialog from 'src/composables/dialogs/useCollectionDialog'
import CreateButton from 'src/components/custom/CreateButton.vue'

import { onMounted, computed, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import ErrorDisplay from 'src/components/custom/ErrorDisplay.vue'
import CollectionCard from 'src/components/custom/CollectionCard.vue'
import { Collection, PatchCollection, PostCollection } from 'src/models/collections'
import { useRouter } from 'vue-router'

const $router = useRouter()
const $q = useQuasar()
const itemsPerPage = computed(() => $q.screen.gt.lg ? 11 : 5)
const VIEW_MODE_STORAGE_KEY = 'collections.viewMode'
const getInitialViewMode = (): 'tiles' | 'table' => {
  const storedMode = localStorage.getItem(VIEW_MODE_STORAGE_KEY)
  return storedMode === 'table' ? 'table' : 'tiles'
}
const viewMode = ref<'tiles' | 'table'>(getInitialViewMode())
const searchQuery = ref('')
const { collections, error, loading, loadCollections, createCollection, updateCollection, deleteCollection } = useCollections()
const filteredCollections = computed(() => {
  if (!searchQuery.value?.trim()) {
    return collections.value
  }
  const query = searchQuery.value.toLowerCase()
  return collections.value.filter((collection) =>
    collection.name.toLowerCase().includes(query)
  )
})
const { currentPage, pageCount, paginatedItems } = usePagination(filteredCollections, itemsPerPage)
const { openCollectionDialog } = useCollectionDialog()

watch(viewMode, (mode) => {
  localStorage.setItem(VIEW_MODE_STORAGE_KEY, mode)
})

onMounted(async () => {
  searchQuery.value = ''
  await loadCollections('xjuric')
})

const handleRefresh = async () => {
  await loadCollections('xjuric')
}

const handleCreate = () => {
  openCollectionDialog({
    dialogType: 'CREATE'
  }).onOk((collectionData: PostCollection) => {
    createCollection({
      ...collectionData,
      userId: 'xjuric'
    })
  })
}

const handleEnter = async (collectionId: string) => {
  await $router.push({ name: 'collectionDetail', params: { collectionId } })
}

const handleEdit = (collection: Collection) => {
  openCollectionDialog({
    dialogType: 'EDIT',
    collection
  }).onOk((updatedData: PatchCollection) => {
    updateCollection(collection.id, updatedData)
  })
}

const handleDelete = (collection: Collection) => {
  $q.dialog({
    title: 'Delete Collection',
    html: true,
    message: `Are you sure you want to delete the collection <strong>${collection.name}</strong>? This action cannot be undone.`,
    ok: {
      label: 'Delete',
      color: 'negative'
    },
    cancel: true
  }).onOk(async () => {
    await deleteCollection(collection.id)
  })
}
</script>
