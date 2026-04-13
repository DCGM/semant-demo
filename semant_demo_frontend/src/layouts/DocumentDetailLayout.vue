<template>
  <q-page class="q-pt-sm">
    <div class="document-detail-topbar q-px-md">
      <q-btn-toggle
        v-model="selectedView"
        unelevated
        toggle-color="primary"
        color="grey-3"
        text-color="dark"
        spread
        :options="viewOptions"
        class="document-detail-toggle"
      />
    </div>

    <q-separator spaced="sm" size="1.5px" />
    <router-view />
  </q-page>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const $route = useRoute()
const $router = useRouter()

const viewOptions = [
  { label: 'V1', value: 'v1' },
  { label: 'V2', value: 'v2' }
]

const getRouteParams = () => ({
  collectionId: $route.params.collectionId ?? '',
  documentId: $route.params.documentId ?? ''
})

const selectedView = computed({
  get: () => ($route.name === 'documentDetailV1' ? 'v1' : 'v2'),
  set: async (value: string) => {
    const targetName = value === 'v1' ? 'documentDetailV1' : 'documentDetailV2'

    console.log('set has been called with value:', value)

    if ($route.name === targetName) {
      return
    }

    await $router.push({
      name: targetName,
      params: getRouteParams()
    })
  }
})
</script>

<style scoped lang="scss">
.document-detail-topbar {
  width: 100%;
  max-width: 280px;
  margin: 0 auto;
}

.document-detail-toggle {
  width: 100%;
}
</style>
