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

      <q-btn-toggle
        v-model="ownership"
        class="q-mr-md"
        unelevated
        no-caps
        toggle-color="primary"
        color="grey-3"
        text-color="grey-8"
        aria-label="Show collections"
        :options="ownershipOptions"
      />

      <q-space />

      <!-- Tile size; the tiles fill the row at this width or wider. -->
      <div v-if="viewMode === 'tiles'" class="tile-size row no-wrap items-center q-mr-md gt-xs">
        <q-icon name="photo_size_select_small" size="20px" color="grey-7" />
        <q-slider
          v-model="tileSize"
          class="q-mx-sm"
          :min="TILE_SIZE_MIN"
          :max="TILE_SIZE_MAX"
          :step="20"
          aria-label="Tile size"
        />
        <q-icon name="photo_size_select_large" size="20px" color="grey-7" />
      </div>

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
    <div v-if="viewMode === 'tiles'" class="collection-tiles q-px-md q-py-md" :style="{ '--tile-size': `${tileSize}px` }">
      <!-- A new collection is the user's own, so not offered among those shared with them. -->
      <CreateCollectionCard v-if="ownership !== 'shared'" @click="handleCreate"/>

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
      :collections="ownedFiltered"
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
import useConfirmDelete from 'src/shared/useConfirmDelete'
import { annotationsOfCollections } from 'src/features/annotations/annotationCounts'
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
// My / Shared with me / All (#479): every collection the user can read is either their own
// or shared with them (`isSharedWithMe`). Remembered in this browser, like the view mode.
type Ownership = 'all' | 'mine' | 'shared'
const OWNERSHIP_STORAGE_KEY = 'collections.ownership'
const readStored = (key: string): string | null => {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
const writeStored = (key: string, value: string) => {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Storage unavailable (private mode, quota) — the choice just won't persist.
  }
}
const storedOwnership = readStored(OWNERSHIP_STORAGE_KEY)
const ownership = ref<Ownership>(storedOwnership === 'mine' || storedOwnership === 'shared' ? storedOwnership : 'all')
watch(ownership, (value) => writeStored(OWNERSHIP_STORAGE_KEY, value))
const myCount = computed(() => collections.value.filter((c) => !c.isSharedWithMe).length)
const ownershipOptions = computed(() => [
  { value: 'mine', label: `My (${myCount.value})` },
  { value: 'shared', label: `Shared with me (${collections.value.length - myCount.value})` },
  { value: 'all', label: `All (${collections.value.length})` }
])
const ownedFiltered = computed(() => {
  if (ownership.value === 'all') return collections.value
  const shared = ownership.value === 'shared'
  return collections.value.filter((c) => !!c.isSharedWithMe === shared)
})

const filteredCollections = computed(() => {
  if (!searchQuery.value?.trim()) {
    return ownedFiltered.value
  }
  const query = searchQuery.value.toLowerCase()
  return ownedFiltered.value.filter((collection) =>
    collection.name.toLowerCase().includes(query)
  )
})

// The smallest tile width in the TILES view (#479); remembered in this browser.
const TILE_SIZE_STORAGE_KEY = 'collections.tileSize'
const TILE_SIZE_MIN = 320
const TILE_SIZE_MAX = 560
const TILE_SIZE_DEFAULT = 340
const storedTileSize = Number(readStored(TILE_SIZE_STORAGE_KEY))
const tileSize = ref(storedTileSize >= TILE_SIZE_MIN && storedTileSize <= TILE_SIZE_MAX ? storedTileSize : TILE_SIZE_DEFAULT)
watch(tileSize, (value) => writeStored(TILE_SIZE_STORAGE_KEY, String(value)))
const { currentPage, pageCount, paginatedItems } = usePagination(filteredCollections, itemsPerPage)
watch(ownership, () => { currentPage.value = 1 })
const { openCollectionDialog } = useCollectionDialog()
const confirmDelete = useConfirmDelete()

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
  confirmDelete({
    title: 'Delete Collection',
    message: `Delete the collection "${collection.name}"?`,
    alsoDeletes: annotationsOfCollections([collection.id])
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

<style scoped>
/* Tiles at least --tile-size wide, as many as fit in a row. */
.collection-tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(var(--tile-size), 100%), 1fr));
  gap: 16px;
}

.tile-size {
  width: 200px;
}
</style>
