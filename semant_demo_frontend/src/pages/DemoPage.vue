<template>
  <q-page class="q-pa-md">
    <div class="row justify-center">
      <span class="text-h6">Demo</span>
    </div>

    <div>
      User collections:
      <div v-if="userCollection">
        <pre>{{ JSON.stringify(userCollection, null, 2) }}</pre>
      </div>
      <div v-else>-</div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useApi } from 'src/composables/useApi'
import { GetCollectionsResponse } from 'src/generated/api'

const api = useApi().default
const userCollection = ref<GetCollectionsResponse | null>(null)

const getUserCollections = async () => {
  await api
    .fetchCollectionsApiCollectionsGet({ userId: 'xuser' })
    .then((collection) => {
      userCollection.value = collection
    })
    .catch((error) => {
      console.error('Error fetching collections:', error)
    })
}

onMounted(async () => {
  console.log('DemoPage mounted')
  await getUserCollections()
})
</script>
