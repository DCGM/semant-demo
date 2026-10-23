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
          :min="TILE_SIZES[0]"
          :max="TILE_SIZES[TILE_SIZES.length - 1]"
          :step="TILE_SIZE_STEP"
          markers
          snap
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
    <div v-if="viewMode === 'tiles'" ref="tilesRef" class="collection-tiles q-px-md q-py-md" :style="{ '--tile-size': `${tileSize}px`, gap: `${TILE_GAP}px` }">
      <!-- A new collection is the user's own, so not offered among those shared with them. -->
      <CreateCollectionCard v-if="showCreateTile" @click="handleCreate"/>

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

import { onBeforeUnmount, onMounted, computed, ref, watch } from 'vue'
import { readStored, writeStored } from 'src/shared/browserStorage'
import { useQuasar } from 'quasar'
import ErrorDisplay from 'src/shared/ui/ErrorDisplay.vue'
import CollectionCard from './CollectionCard.vue'
import useConfirmDelete from 'src/shared/useConfirmDelete'
import { annotationsOfCollections } from 'src/features/annotations/annotationCounts'
import { Collection, PatchCollection, PostCollection } from 'src/generated/api'
import { useRouter } from 'vue-router'

const $router = useRouter()
const $q = useQuasar()
const VIEW_MODE_STORAGE_KEY = 'collections.viewMode'
const getInitialViewMode = (): 'tiles' | 'table' => {
  const storedMode = readStored(VIEW_MODE_STORAGE_KEY)
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

// The tile width in the TILES view (#479), in a few distinct sizes the slider snaps to,
// like a file manager's zoom; remembered in this browser.
const TILE_SIZE_STORAGE_KEY = 'collections.tileSize'
const TILE_SIZE_STEP = 60
const TILE_SIZES = [320, 380, 440, 500, 560]
const nearestTileSize = (size: number) =>
  TILE_SIZES.reduce((best, s) => Math.abs(s - size) < Math.abs(best - size) ? s : best)
const storedTileSize = Number(readStored(TILE_SIZE_STORAGE_KEY))
const tileSize = ref(storedTileSize > 0 ? nearestTileSize(storedTileSize) : TILE_SIZES[0])
watch(tileSize, (value) => writeStored(TILE_SIZE_STORAGE_KEY, String(value)))

// A page of tiles fills whole rows: as many tiles per row as fit at the chosen size
// (measured from the grid's width; the window's without ResizeObserver), 3 rows on wide
// screens and 2 otherwise, and rows enough for at least MIN_TILES_PER_PAGE tiles (a phone
// has one tile a row), less the create tile where it is shown.
const TILE_GAP = 16
const MIN_TILES_PER_PAGE = 6
const tilesRef = ref<HTMLElement | null>(null)
const tilesWidth = ref(window.innerWidth)
const tilesObserver = typeof ResizeObserver === 'undefined'
  ? null
  : new ResizeObserver(([entry]) => { tilesWidth.value = entry.contentRect.width })
watch(tilesRef, (el, previous) => {
  if (previous) tilesObserver?.unobserve(previous)
  if (el) tilesObserver?.observe(el)
})
onBeforeUnmount(() => tilesObserver?.disconnect())
const showCreateTile = computed(() => ownership.value !== 'shared')
const itemsPerPage = computed(() => {
  const perRow = Math.max(1, Math.floor((tilesWidth.value + TILE_GAP) / (tileSize.value + TILE_GAP)))
  const rows = Math.max($q.screen.gt.md ? 3 : 2, Math.ceil(MIN_TILES_PER_PAGE / perRow))
  return perRow * rows - (showCreateTile.value ? 1 : 0)
})
const { currentPage, pageCount, paginatedItems } = usePagination(filteredCollections, itemsPerPage)
watch(ownership, () => { currentPage.value = 1 })
// Fewer pages (larger pages, or a filter): stay on the last one there is.
watch(pageCount, (count) => { if (currentPage.value > Math.max(1, count)) currentPage.value = Math.max(1, count) })
const { openCollectionDialog } = useCollectionDialog()
const confirmDelete = useConfirmDelete()

watch(viewMode, (mode) => {
  writeStored(VIEW_MODE_STORAGE_KEY, mode)
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
    // A new collection is the user's own: show it, not the collections shared with them.
    if (ownership.value === 'shared') ownership.value = 'mine'
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
/* Tiles exactly --tile-size wide (narrower only on a narrower screen), as many as fit in
   a row; like a file manager's icons, each size step shows, and the rest of a row stays
   empty. */
.collection-tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, min(var(--tile-size), 100%));
  /* gap: set from TILE_GAP, which the page size is computed with */
}

.tile-size {
  width: 200px;
}
</style>
