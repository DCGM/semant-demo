<template>
  <q-page class="q-pt-sm">
    <div class="collection-topbar q-px-md q-pb-xs">
      <div class="collection-header">
        <div class="collection-page-kicker">Collection workspace</div>
        <div class="collection-title-row">
          <q-btn
            flat
            round
            dense
            icon="arrow_back"
            :to="{ name: 'collections' }"
            class="collection-back-btn"
          >
            <q-tooltip>Back to Collections</q-tooltip>
          </q-btn>
          <q-icon name="folder_open" size="24px" color="primary" class="collection-title-icon" />
          <h1 class="collection-page-title">{{ activeCollectionLabel }}</h1>
        </div>
      </div>

      <q-tabs indicator-color="primary" active-class="active-tab text-primary" narrow-indicator inline-label class="collection-tabs" align="justify">
        <q-route-tab
          name="documents_tagging"
          label="Documents & tagging"
          icon="library_books"
          :to="{ name: 'collectionDocumentsTagging' }"
        />
        <q-route-tab
          name="overview"
          label="Overview"
          icon="dashboard"
          :to="{ name: 'collectionOverview' }"
        />
        <q-separator vertical size="1.8px" inset />
        <q-separator vertical size="1.8px" inset />
        <q-route-tab
          name="tags"
          label="Tags"
          icon="local_offer"
          :to="{ name: 'collectionTags' }"
        />
        <q-separator vertical size="1.8px" inset />
        <q-route-tab
          name="members"
          label="Members"
          icon="people"
          :to="{ name: 'collectionMembers' }"
        />
      </q-tabs>
    </div>

    <q-separator spaced="sm" size="1.7px" />
    <router-view />
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import useCollections from 'src/composables/useCollections'

const $route = useRoute()
const { activeCollection, loadCollection } = useCollections()

const collectionId = computed(() => {
  const value = $route.params.collectionId
  return typeof value === 'string' ? value : ''
})

const activeCollectionLabel = computed(() =>
  activeCollection.value?.id === collectionId.value ? activeCollection.value.name : ''
)

onMounted(() => {
  if (collectionId.value) {
    loadCollection(collectionId.value)
  }
})

watch(collectionId, (newId) => {
  if (newId) {
    loadCollection(newId)
  }
})
</script>

<style scoped lang="scss">
.active-tab {
  background-color: #e8f0fe;
  border-radius: 5px;
}

.collection-topbar {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.collection-page-kicker {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(0, 0, 0, 0.52);
  margin-bottom: 4px;
}

.collection-header {
  padding: 2px 0;
  flex: 0 1 420px;
}

.collection-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.collection-back-btn {
  color: rgba(0, 0, 0, 0.72);
}

.collection-title-icon {
  flex: 0 0 auto;
}

.collection-page-title {
  margin: 0;
  font-size: clamp(1.18rem, 1.08rem + 0.7vw, 1.6rem);
  font-weight: 700;
  line-height: 1.15;
  color: #1f2a37;
}

.collection-tabs {
  flex: 1 1 520px;
  min-width: 380px;
  width: 100%;
}

@media (max-width: 900px) {
  .collection-tabs {
    min-width: 0;
    width: 100%;
  }
}
</style>
