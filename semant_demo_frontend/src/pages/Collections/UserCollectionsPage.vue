<template>
  <q-page padding>
    <PageTitle title="Collections" />
    <div class="row q-my-sm">
      <RefreshButton @click="handleRefresh" />
      <CreateButton @click="handleCreate" />

      <q-space />

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
    <div class="row q-col-gutter-md">
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
    <div class="row justigy-center q-mt-md lt-md">
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

import usePagination from 'src/composables/usePagination'
import useCollections from 'src/composables/useCollections'
import useCollectionDialog from 'src/composables/dialogs/useCollectionDialog'
import CreateButton from 'src/components/custom/CreateButton.vue'

import { onMounted, computed } from 'vue'
import { useQuasar } from 'quasar'
import ErrorDisplay from 'src/components/custom/ErrorDisplay.vue'
import CollectionCard from 'src/components/custom/CollectionCard.vue'
import { Collection, PatchCollection, PostCollection } from 'src/models/collection'
import { useRouter } from 'vue-router'

const $router = useRouter()
const $q = useQuasar()
const itemsPerPage = computed(() => $q.screen.gt.lg ? 11 : 5)
const { collections, error, loading, loadCollections, createCollection, updateCollection, deleteCollection } = useCollections()
const { currentPage, pageCount, paginatedItems } = usePagination(collections, itemsPerPage)
const { openCollectionDialog } = useCollectionDialog()

onMounted(async () => {
  await loadCollections('xjuric')
})

const handleRefresh = async () => {
  await loadCollections('xjuric')
}

const handleCreate = () => {
  openCollectionDialog({
    dialogType: 'CREATE'
  }).onOk((collectionData: PostCollection) => {
    createCollection('xjuric', collectionData)
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
  }).onOk(() => {
    deleteCollection(collection.id)
  })
}

</script>
