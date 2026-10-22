<template>
  <q-page class="q-pt-md" p>
    <PageTitle title="Collections" />
    <div class="row items-center q-my-sm q-px-md">
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

      <!-- The table view pages with the table's own control. -->
      <q-pagination
        v-if="viewMode === 'tiles'"
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
    <div v-if="viewMode === 'tiles'" class="row q-col-gutter-md q-px-md q-py-md">
      <CreateCollectionCard @click="handleCreate"/>

      <CollectionCard
        v-for="(collection, index) in paginatedItems"
        :key="collection.id ?? index"
        :collection="collection"
        @enter="handleEnter"
        @edit="handleEdit"
        @delete="handleDelete"
        @share="handleShare"
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
      @deleteMany="handleDeleteMany"
      @share="handleShare"
      @shareMany="handleShareMany"
    />
    <div v-if="viewMode === 'tiles'" class="row justify-center q-mt-md lt-md">
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
  </q-page>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import PageTitle from 'src/shared/ui/PageTitle.vue'
import CreateCollectionCard from './CreateCollectionCard.vue'
import CollectionsTable from './CollectionsTable.vue'

import usePagination from 'src/shared/usePagination'
import { useUserCollectionsStore } from './userCollectionsStore'
import useCollectionDialog from './useCollectionDialog'
import CreateButton from 'src/shared/ui/CreateButton.vue'

import { onMounted, computed, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import ErrorDisplay from 'src/shared/ui/ErrorDisplay.vue'
import CollectionCard from './CollectionCard.vue'
import { Collection, PatchCollection, PostCollection } from 'src/generated/api'
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
const collectionsStore = useUserCollectionsStore()
const { collections, error, loading } = storeToRefs(collectionsStore)
const { fetchCollections, createCollection, updateCollection, deleteCollection, deleteManyCollections, shareManyCollections } = collectionsStore
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
  await fetchCollections()
})

const handleCreate = () => {
  openCollectionDialog({
    dialogType: 'CREATE'
  }).onOk(async (collectionData: PostCollection) => {
    await createCollection(collectionData)
  })
}

const handleEnter = async (collectionId: string) => {
  await $router.push({ name: 'collectionDetail', params: { collectionId } })
}

const handleShare = async (collection: Collection) => {
  await $router.push({ name: 'collectionMembers', params: { collectionId: collection.id } })
}

const handleEdit = (collection: Collection) => {
  openCollectionDialog({
    dialogType: 'EDIT',
    collection
  }).onOk(async (updatedData: PatchCollection) => {
    await updateCollection(collection.id, updatedData)
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

const handleDeleteMany = (collectionIds: string[]) => {
  deleteManyCollections(collectionIds)
}

const handleShareMany = ({ collectionIds, userId }: { collectionIds: string[]; userId: string }) => {
  shareManyCollections(collectionIds, userId)
}
</script>
