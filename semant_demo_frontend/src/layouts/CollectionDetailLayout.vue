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
          <button
            v-if="activeCollectionColor"
            type="button"
            class="collection-color-button"
            aria-label="Edit collection color"
            @click="openCollectionColorPicker"
          >
            <span
              class="collection-color-dot"
              :style="{ backgroundColor: activeCollectionColor }"
              aria-label="Collection color"
            />
            <q-tooltip>Click to edit color</q-tooltip>
          </button>
          <q-dialog v-model="showColorPicker">
            <q-card>
              <q-card-section>
                <q-color v-model="tempColor" format="hex" />
              </q-card-section>
              <q-card-section align="right">
                <q-btn
                  flat
                  label="Cancel"
                  color="primary"
                  :disable="isSavingColor"
                  @click="closeColor"
                />
                <q-btn
                  unelevated
                  label="Confirm"
                  color="primary"
                  :loading="isSavingColor"
                  :disable="isSavingColor"
                  @click="submitColorEdit"
                />
              </q-card-section>
            </q-card>
          </q-dialog>
          <q-input
            v-if="isEditingName"
            v-model="editableCollectionName"
            dense
            outlined
            autofocus
            class="collection-title-input"
            :disable="isSavingName"
            @keyup.enter="submitNameEdit"
            @keyup.esc="cancelNameEdit"
          >
            <template #append>
              <q-btn
                flat
                round
                dense
                icon="check"
                color="positive"
                :disable="isNameSaveDisabled"
                :loading="isSavingName"
                @click="submitNameEdit"
              />
              <q-btn
                flat
                round
                dense
                icon="close"
                color="negative"
                :disable="isSavingName"
                @click="cancelNameEdit"
              />
            </template>
          </q-input>
          <button
            v-else
            type="button"
            class="collection-title-button"
            :disabled="!activeCollectionLabel"
            @click="startNameEdit"
          >
            <h1 class="collection-page-title">{{ activeCollectionLabel }}</h1>
            <q-tooltip v-if="activeCollectionLabel">Click to edit</q-tooltip>
          </button>
        </div>
      </div>

      <q-tabs
        indicator-color="primary"
        active-class="active-tab text-primary"
        narrow-indicator
        inline-label
        class="collection-tabs"
        align="justify"
        >
        <q-route-tab
          name="overview"
          label="Overview"
          icon="dashboard"
          :to="{ name: 'collectionOverview' }"
        />
        <q-route-tab
          name="documents_tagging"
          label="Documents & tagging"
          icon="library_books"
          :to="{ name: 'collectionDocumentsTagging' }"
        />
        <q-separator vertical size="1.8px" inset />
        <q-separator vertical size="1.8px" inset />
        <q-route-tab
          name="tags"
          label="Tags"
          icon="label"
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
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import useCollections from 'src/composables/useCollections'
import useColorPicker from 'src/composables/useColorPicker'

const $route = useRoute()
const { activeCollection, loadCollection, updateCollection } = useCollections()

const isEditingName = ref(false)
const isSavingName = ref(false)
const isSavingColor = ref(false)
const editableCollectionName = ref('')

const {
  currentColor,
  tempColor,
  showColorPicker,
  openColorPicker,
  confirmColor,
  closeColor
} = useColorPicker('#1976d2')

const collectionId = computed(() => {
  const value = $route.params.collectionId
  return typeof value === 'string' ? value : ''
})

const activeCollectionLabel = computed(() =>
  activeCollection.value?.id === collectionId.value
    ? activeCollection.value.name
    : ''
)

const activeCollectionColor = computed(() =>
  activeCollection.value?.id === collectionId.value
    ? activeCollection.value.color
    : null
)

const normalizedEditedName = computed(() => editableCollectionName.value.trim())

const isNameSaveDisabled = computed(() =>
  isSavingName.value ||
  !normalizedEditedName.value ||
  normalizedEditedName.value === activeCollectionLabel.value
)

const startNameEdit = () => {
  if (!activeCollectionLabel.value) return
  editableCollectionName.value = activeCollectionLabel.value
  isEditingName.value = true
}

const cancelNameEdit = () => {
  isEditingName.value = false
  editableCollectionName.value = activeCollectionLabel.value
}

const submitNameEdit = async () => {
  if (!collectionId.value || isNameSaveDisabled.value) return

  const updatedName = normalizedEditedName.value
  isSavingName.value = true
  await updateCollection(collectionId.value, { name: updatedName })
  await loadCollection(collectionId.value)
  isSavingName.value = false

  isEditingName.value = false
}

const openCollectionColorPicker = () => {
  if (!activeCollectionColor.value) return
  currentColor.value = activeCollectionColor.value
  openColorPicker()
}

const submitColorEdit = async () => {
  confirmColor()

  if (currentColor.value === activeCollectionColor.value) {
    return
  }

  isSavingColor.value = true
  await updateCollection(collectionId.value, { color: currentColor.value })
  isSavingColor.value = false

  closeColor()
  await loadCollection(collectionId.value)
}

onMounted(async () => {
  await loadCollection(collectionId.value)
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

.collection-title-button {
  border: 0;
  padding: 0;
  background: transparent;
  cursor: text;
  text-align: left;
}

.collection-title-button:disabled {
  cursor: default;
}

.collection-title-input {
  width: min(420px, 65vw);
}

.collection-back-btn {
  color: rgba(0, 0, 0, 0.72);
}

.collection-color-button {
  border: 0;
  padding: 0;
  background: transparent;
  display: inline-flex;
  align-items: center;
}

.collection-color-dot {
  width: 16px;
  height: 16px;
  border-radius: 999px;
  border: 1px solid rgba(0, 0, 0, 0.2);
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.9);
  flex: 0 0 auto;
  cursor: pointer;
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
