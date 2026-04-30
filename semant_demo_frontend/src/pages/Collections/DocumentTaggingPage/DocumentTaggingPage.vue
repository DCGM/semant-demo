<template>
  <q-page class="q-pa-lg">
    <!-- <div class="row items-start q-mb-lg">
      <q-btn flat round dense icon="arrow_back" @click="goBack" class="q-mr-md">
        <q-tooltip>Go back</q-tooltip>
      </q-btn>
      <div>
        <h5 class="q-ma-none">
          {{ documentDetail?.document.title || 'Untitled Document' }}
        </h5>
      </div>
      <q-space />
    </div> -->

    <TaggingPage
      :collection-id="props.collectionId"
      :document-id="props.documentId"
    />

    <!-- <q-separator class="q-my-md" />

    <div class="row q-gutter-md">
      <q-btn
        color="negative"
        label="Remove from Collection"
        icon="delete"
        @click="handleRemoveFromCollection"
      />
    </div> -->
  </q-page>
</template>

<script setup lang="ts">
import TaggingPage from './components/TaggingPage.vue'

interface Props {
  collectionId: string
  documentId: string
}

const props = defineProps<Props>()
</script>

<style scoped></style>
