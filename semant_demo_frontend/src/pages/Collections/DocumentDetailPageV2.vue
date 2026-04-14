<template>
  <DocumentTaggingPage
    :collection-id="props.collectionId"
    :document-id="props.documentId"
  />
</template>

<script setup lang="ts">
import DocumentTaggingPage from './DocumentTaggingPage/DocumentTaggingPage.vue'

interface Props {
  collectionId: string
  documentId: string
}

const props = defineProps<Props>()
</script>
