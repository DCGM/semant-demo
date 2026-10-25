<template>
  <q-page class="q-pt-sm">
    <div class="collection-topbar q-px-md q-pb-xs">
      <div class="collection-header">
        <BackLink :to="{ name: 'collections' }" label="Collections" aria-label="Back to collections" />
        <div class="collection-title-row">
          <button
            v-if="activeCollectionColor"
            type="button"
            class="collection-color-button"
            aria-label="Edit collection color"
            :disabled="!rights.editMetadata"
            @click="openCollectionColorPicker"
          >
            <span
              class="collection-color-dot"
              :style="{ backgroundColor: activeCollectionColor }"
              aria-label="Collection color"
            />
            <q-tooltip v-if="rights.editMetadata">Click to edit color</q-tooltip>
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
          <!-- A long name is cut off with an ellipsis (#479), so the tooltips show it whole.
               Only the owner gets a button: a disabled one would never show its tooltip. -->
          <button
            v-else-if="activeCollectionLabel && rights.editMetadata"
            type="button"
            class="collection-title-button"
            @click="startNameEdit"
          >
            <h1 class="collection-page-title">{{ activeCollectionLabel }}</h1>
            <q-tooltip>{{ activeCollectionLabel }}<br>Click to edit</q-tooltip>
          </button>
          <h1 v-else class="collection-page-title">
            {{ activeCollectionLabel }}
            <q-tooltip v-if="activeCollectionLabel">{{ activeCollectionLabel }}</q-tooltip>
          </h1>
        </div>
      </div>

      <q-tabs
        indicator-color="primary"
        active-class="active-tab text-primary"
        narrow-indicator
        inline-label
        outside-arrows
        class="collection-tabs"
        align="justify"
        >
        <q-route-tab
          name="overview"
          label="Overview"
          icon="dashboard"
          :to="{ name: 'collectionOverview' }"
        />
        <q-separator vertical size="1.8px" inset />
        <q-route-tab
          name="documents_tagging"
          label="Documents & tagging"
          icon="library_books"
          :to="{ name: 'collectionDocumentsTagging' }"
        />
        <q-separator vertical size="1.8px" inset />
        <q-route-tab
          name="annotations"
          label="Annotations"
          icon="format_quote"
          :to="{ name: 'collectionAnnotations' }"
        />
        <q-separator vertical size="1.8px" inset />
        <!-- Leads to the part shown last, so the tab stays active on either of its routes. -->
        <q-route-tab
          name="tags"
          label="Tags & attributes"
          icon="label"
          :to="{ name: $route.name === 'collectionAttributes' ? 'collectionAttributes' : 'collectionTags' }"
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
import { storeToRefs } from 'pinia'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useUserCollectionsStore } from './userCollectionsStore'
import useColorPicker from 'src/shared/useColorPicker'
import { collectionRights } from './permissions'
import BackLink from 'src/shared/ui/BackLink.vue'
import { overlayOpen } from 'src/shared/overlays'

const $route = useRoute()
const collectionsStore = useUserCollectionsStore()
const { activeCollection } = storeToRefs(collectionsStore)
const { fetchCollection, updateCollection } = collectionsStore

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

// Name and color are owner-only metadata (ADR 0007).
const rights = computed(() =>
  collectionRights(activeCollection.value?.id === collectionId.value ? activeCollection.value : null)
)

const normalizedEditedName = computed(() => editableCollectionName.value.trim())

// An unchanged name may be confirmed too; it just closes the editor.
const isNameSaveDisabled = computed(() => isSavingName.value || !normalizedEditedName.value)

const startNameEdit = () => {
  if (!activeCollectionLabel.value || !rights.value.editMetadata) return
  editableCollectionName.value = activeCollectionLabel.value
  isEditingName.value = true
}

// A save already sent cannot be taken back, so the editor stays until it is answered.
const cancelNameEdit = () => {
  if (isSavingName.value) return
  isEditingName.value = false
  editableCollectionName.value = activeCollectionLabel.value
}

const submitNameEdit = async () => {
  if (!collectionId.value || isNameSaveDisabled.value) return

  const updatedName = normalizedEditedName.value
  if (updatedName === activeCollectionLabel.value) {
    isEditingName.value = false
    return
  }
  isSavingName.value = true
  try {
    // The store keeps the saved collection; a failed rename keeps the editor open with the
    // typed name (the store reports the error).
    if (await updateCollection(collectionId.value, { name: updatedName })) isEditingName.value = false
  } finally {
    isSavingName.value = false
  }
}

// Escape cancels the name edit also when the focus left the input, but not when it is
// meant for another field (e.g. a search box) or closes a dialog or menu (the color picker).
const OTHER_FIELD = 'input, textarea, select, [contenteditable=""], [contenteditable="true"], [role="combobox"]'
const onEditKeydown = (e: KeyboardEvent) => {
  if (e.key !== 'Escape' || e.defaultPrevented || e.isComposing || overlayOpen()) return
  const target = e.target
  if (target instanceof Element && target.closest(OTHER_FIELD) && !target.closest('.collection-title-input')) return
  cancelNameEdit()
}
watch(isEditingName, (editing) => {
  if (editing) window.addEventListener('keydown', onEditKeydown)
  else window.removeEventListener('keydown', onEditKeydown)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onEditKeydown))

const openCollectionColorPicker = () => {
  if (!activeCollectionColor.value || !rights.value.editMetadata) return
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
}

onMounted(async () => {
  await fetchCollection(collectionId.value)
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
  // The tabs keep their place; a long name shrinks and ends in an ellipsis (#479).
  flex-wrap: nowrap;
}

.collection-header {
  padding: 2px 0;
  flex: 0 1 auto;
  min-width: 12rem;
}

.collection-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.collection-title-button {
  min-width: 0;
  border: 0;
  padding: 0;
  background: transparent;
  cursor: text;
  text-align: left;
}

.collection-title-input {
  width: min(350px, 65vw);
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
  max-width: 36ch;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.collection-tabs {
  // Shrinks with scroll arrows when the tabs do not fit, rather than overflowing the page;
  // the arrows sit outside the tabs (outside-arrows), so they never cover the last one (#489).
  flex: 1 1 auto;
  min-width: 0;
  // A margin, not q-pl-md: outside-arrows sets the tabs' own padding.
  margin-left: 16px;
}

@media (max-width: 900px) {
  .collection-topbar {
    flex-wrap: wrap;
  }

  .collection-tabs {
    min-width: 0;
    width: calc(100% - 16px);
  }
}
</style>
