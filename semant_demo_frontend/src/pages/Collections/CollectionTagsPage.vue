<template>
  <q-page>
    <TagsTable
      :tags="tags"
      :loading="loading"
      @refresh="handleRefresh"
    />
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'

import useTags from 'src/composables/useTags'
import TagsTable from 'src/components/tables/TagsTable.vue'

const $route = useRoute()
const { tags, loading, loadTags } = useTags()

const collectionId = computed<string>(() => {
  const value = $route.params.collectionId
  if (typeof value !== 'string') {
    throw new Error('Missing required route param: collectionId')
  }
  return value
})

const handleRefresh = async () => {
  await loadTags(collectionId.value)
}

onMounted(async () => {
  await handleRefresh()
})
</script>
