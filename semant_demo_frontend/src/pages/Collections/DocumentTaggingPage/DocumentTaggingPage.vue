<template>
  <q-page class="q-pa-lg">
    <div class="row items-center q-mb-lg">
      <div>
        <h5 class="q-ma-none">Tag Document</h5>
        <p class="text-caption text-grey-7 q-mt-sm">
          Document: {{ documentId }}
        </p>
      </div>
      <q-space />
      <q-btn flat round dense icon="arrow_back" @click="goBack" class="q-mr-md">
        <q-tooltip>Go back</q-tooltip>
      </q-btn>
    </div>

  <TaggingPage :collection-id="props.collectionId" />

    <q-separator class="q-my-md" />

    <div class="row q-gutter-md">
      <q-btn
        color="negative"
        label="Remove from Collection"
        icon="delete"
        @click="handleRemoveFromCollection"
      />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import useDocuments from 'src/composables/useDocuments'
import { useDocumentsRepository } from 'src/repositories/useDocumentsRepository'
import { successNotification, errorNotification } from 'src/utils/notification'
import { onMounted } from 'vue'
import TaggingPage from './components/TaggingPage.vue'
import { useTagging } from './composables/useTagging'

interface Props {
  collectionId: string
  documentId: string
}

const props = defineProps<Props>()
const router = useRouter()
const documentsRepository = useDocumentsRepository()
const { loadDocumentsByCollection } = useDocuments()
const { collectionChunks, getCollectionChunksPaged } = useTagging()

onMounted(() => {
  getCollectionChunksPaged(props.collectionId)
})

const goBack = () => {
  router.push({
    name: 'collectionDocumentsTagging',
    params: { collectionId: props.collectionId }
  })
}

const handleRemoveFromCollection = async () => {
  try {
    const removed = await documentsRepository.removeFromCollection(
      props.documentId,
      props.collectionId
    )
    if (removed) {
      successNotification('Document removed from collection')

      // Refresh documents list
      await loadDocumentsByCollection(props.collectionId)

      // Go back to documents list
      goBack()
      return
    }
    errorNotification('Failed to remove document from collection')
  } catch (error) {
    errorNotification('Failed to remove document from collection')
    console.error('Error removing document:', error)
  }
}
</script>

<style scoped></style>
