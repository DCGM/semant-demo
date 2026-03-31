<template>
  <div class="collection-overview q-pa-md">
    <q-card flat bordered class="panel-card">
      <q-card-section class="q-pb-sm">
        <div class="text-subtitle1 text-weight-medium">Collection Details</div>
      </q-card-section>

      <q-card-section class="q-pt-none">
        <q-markup-table flat separator="horizontal" class="overview-table">
          <tbody>
            <tr>
              <th class="details-key">Name</th>
              <td class="details-value">
                <div v-if="isEditingName" class="edit-cell">
                  <q-input
                    v-model="editableName"
                    dense
                    outlined
                    maxlength="50"
                    counter
                    :disable="isSavingName"
                    @keyup.enter="submitNameEdit"
                    @keyup.esc="cancelNameEdit"
                  />
                  <div class="edit-actions">
                    <q-btn
                      flat
                      color="primary"
                      label="Cancel"
                      :disable="isSavingName"
                      @click="cancelNameEdit"
                    />
                    <q-btn
                      unelevated
                      color="primary"
                      label="Save"
                      :loading="isSavingName"
                      :disable="isNameSaveDisabled"
                      @click="submitNameEdit"
                    />
                  </div>
                </div>
                <div v-else class="readonly-cell">
                  <span>{{ activeCollection?.name || '-' }}</span>
                  <q-btn
                    flat
                    dense
                    icon="edit"
                    label="Edit"
                    :disable="!activeCollection"
                    @click="startNameEdit"
                  />
                </div>
              </td>
            </tr>

            <tr>
              <th class="details-key">Description</th>
              <td class="details-value">
                <div v-if="isEditingDescription" class="edit-cell">
                  <q-input
                    v-model="editableDescription"
                    type="textarea"
                    outlined
                    autogrow
                    maxlength="1000"
                    counter
                    :disable="isSavingDescription"
                    @keyup.esc="cancelDescriptionEdit"
                  />
                  <div class="edit-actions">
                    <q-btn
                      flat
                      color="primary"
                      label="Cancel"
                      :disable="isSavingDescription"
                      @click="cancelDescriptionEdit"
                    />
                    <q-btn
                      unelevated
                      color="primary"
                      label="Save"
                      :loading="isSavingDescription"
                      :disable="isDescriptionSaveDisabled"
                      @click="submitDescriptionEdit"
                    />
                  </div>
                </div>
                <div v-else class="readonly-cell description-row">
                  <span class="description-inline" :class="{ 'description-empty': !normalizedDescription }">
                    {{ normalizedDescription || 'No description yet.' }}
                  </span>
                  <q-btn
                    flat
                    dense
                    icon="edit"
                    label="Edit"
                    :disable="!activeCollection"
                    @click="startDescriptionEdit"
                  />
                </div>
              </td>
            </tr>

            <tr>
              <th class="details-key">Color</th>
              <td class="details-value">
                <div class="readonly-cell">
                  <div
                    v-if="activeCollectionColor"
                    class="collection-color-display"
                    aria-label="Collection color"
                  >
                    <span
                      class="collection-color-dot"
                      :style="{ backgroundColor: activeCollectionColor }"
                      aria-label="Collection color"
                    />
                    <span class="collection-color-code">{{ activeCollectionColor }}</span>
                  </div>
                  <span v-else>-</span>
                  <q-btn
                    flat
                    dense
                    icon="edit"
                    label="Edit"
                    :disable="!activeCollectionColor || isSavingColor"
                    @click="openCollectionColorPicker"
                  />
                </div>

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
              </td>
            </tr>

            <tr>
              <th class="details-key">Owner</th>
              <td class="details-value">{{ activeCollection?.userId || '-' }}</td>
            </tr>

            <tr>
              <th class="details-key">Created</th>
              <td class="details-value">{{ createdAtText }}</td>
            </tr>

            <tr>
              <th class="details-key">Updated</th>
              <td class="details-value">{{ updatedAtText }}</td>
            </tr>
          </tbody>
        </q-markup-table>
      </q-card-section>
    </q-card>

    <q-card flat bordered class="panel-card q-mt-lg">
      <q-card-section class="q-pb-sm">
        <div class="statistics-header">
          <div class="text-subtitle1 text-weight-medium">Statistics</div>
          <div class="statistics-subtitle">Quick overview of collection activity and coverage</div>
        </div>
      </q-card-section>

      <q-card-section class="q-pt-none">
        <div class="row q-col-gutter-md q-mt-xs">
          <div
            v-for="stat in statCards"
            :key="stat.key"
            class="col-12 col-sm-6 col-lg-4"
          >
            <q-card flat bordered class="stat-card">
              <q-card-section class="row items-center q-pb-xs">
                <q-icon :name="stat.icon" size="20px" class="q-mr-sm" :color="stat.color" />
                <div class="text-caption text-grey-7">{{ stat.label }}</div>
              </q-card-section>
              <q-card-section class="q-pt-none">
                <div class="stat-value">{{ stat.value }}</div>
                <div class="stat-helper">{{ stat.helper }}</div>
              </q-card-section>
            </q-card>
          </div>
      </div>
      </q-card-section>
    </q-card>
    <ErrorDisplay class="q-mt-md" :error="error" />
    <q-inner-loading :showing="loading" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import useCollections from 'src/composables/useCollections'
import useColorPicker from 'src/composables/useColorPicker'
import ErrorDisplay from 'src/components/custom/ErrorDisplay.vue'

const $route = useRoute()
const {
  activeCollection,
  activeCollectionStats,
  loadCollection,
  loadCollectionStats,
  updateCollection,
  loading,
  error
} = useCollections()

const isEditingDescription = ref(false)
const isSavingDescription = ref(false)
const editableDescription = ref('')
const isEditingName = ref(false)
const isSavingName = ref(false)
const isSavingColor = ref(false)
const editableName = ref('')

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

const normalizedDescription = computed(() => (activeCollection.value?.description ?? '').trim())
const normalizedEditedDescription = computed(() => editableDescription.value.trim())
const normalizedName = computed(() => (activeCollection.value?.name ?? '').trim())
const normalizedEditedName = computed(() => editableName.value.trim())
const activeCollectionColor = computed(() => activeCollection.value?.color ?? null)

const isNameSaveDisabled = computed(() =>
  isSavingName.value ||
  !normalizedEditedName.value ||
  normalizedEditedName.value === normalizedName.value
)

const isDescriptionSaveDisabled = computed(() =>
  isSavingDescription.value ||
  normalizedEditedDescription.value === normalizedDescription.value
)

const refreshOverviewData = async () => {
  if (!collectionId.value) return
  await loadCollection(collectionId.value)
  await loadCollectionStats(collectionId.value)
}

const createdAtText = computed(() =>
  activeCollection.value?.createdAt
    ? activeCollection.value.createdAt.toLocaleString()
    : '-'
)

const updatedAtText = computed(() =>
  activeCollection.value?.updatedAt
    ? activeCollection.value.updatedAt.toLocaleString()
    : '-'
)

const statCards = computed(() => {
  const stats = activeCollectionStats.value

  return [
    {
      key: 'documents',
      label: 'Documents in Collection',
      value: stats?.documentsCount ?? 0,
      helper: 'Number of linked documents',
      icon: 'description',
      color: 'primary'
    },
    {
      key: 'chunks',
      label: 'Chunks in Collection',
      value: stats?.chunksCount ?? 0,
      helper: 'Text chunks assigned to this collection',
      icon: 'notes',
      color: 'secondary'
    },
    {
      key: 'annotations',
      label: 'Annotations in Collection',
      value: stats?.annotationsCount ?? 0,
      helper: 'Sum of chunk-tag annotation links',
      icon: 'sell',
      color: 'accent'
    },
    {
      key: 'taggedChunks',
      label: 'Tagged Chunks',
      value: stats?.taggedChunksCount ?? 0,
      helper: 'Chunks with at least one annotation',
      icon: 'task_alt',
      color: 'positive'
    },
    {
      key: 'untaggedChunks',
      label: 'Untagged Chunks',
      value: stats?.untaggedChunksCount ?? 0,
      helper: 'Chunks without annotations',
      icon: 'do_not_disturb_on',
      color: 'warning'
    },
    {
      key: 'tags',
      label: 'Tags in Collection',
      value: stats?.tagsCount ?? 0,
      helper: 'Defined tags for this collection',
      icon: 'label',
      color: 'teal'
    }
  ]
})

const startDescriptionEdit = () => {
  editableDescription.value = activeCollection.value?.description ?? ''
  isEditingDescription.value = true
}

const startNameEdit = () => {
  editableName.value = activeCollection.value?.name ?? ''
  isEditingName.value = true
}

const cancelDescriptionEdit = () => {
  editableDescription.value = activeCollection.value?.description ?? ''
  isEditingDescription.value = false
}

const cancelNameEdit = () => {
  editableName.value = activeCollection.value?.name ?? ''
  isEditingName.value = false
}

const submitDescriptionEdit = async () => {
  if (!collectionId.value || isDescriptionSaveDisabled.value) return

  const descriptionPayload = normalizedEditedDescription.value || null
  isSavingDescription.value = true

  await updateCollection(collectionId.value, { description: descriptionPayload })
  await refreshOverviewData()

  isSavingDescription.value = false
  if (!error.value) {
    isEditingDescription.value = false
  }
}

const submitNameEdit = async () => {
  if (!collectionId.value || isNameSaveDisabled.value) return

  isSavingName.value = true
  await updateCollection(collectionId.value, { name: normalizedEditedName.value })
  await refreshOverviewData()

  isSavingName.value = false
  if (!error.value) {
    isEditingName.value = false
  }
}

const openCollectionColorPicker = () => {
  if (!activeCollectionColor.value) return
  currentColor.value = activeCollectionColor.value
  openColorPicker()
}

const submitColorEdit = async () => {
  if (!collectionId.value || !activeCollectionColor.value) return

  confirmColor()

  if (currentColor.value === activeCollectionColor.value) {
    closeColor()
    return
  }

  isSavingColor.value = true
  await updateCollection(collectionId.value, { color: currentColor.value })
  await refreshOverviewData()
  isSavingColor.value = false

  if (!error.value) {
    closeColor()
  }
}

watch(collectionId, async (id) => {
  isEditingDescription.value = false
  isEditingName.value = false
  editableDescription.value = ''
  editableName.value = ''
  if (!id) return

  await refreshOverviewData()
  editableName.value = activeCollection.value?.name ?? ''
  editableDescription.value = activeCollection.value?.description ?? ''
}, { immediate: true })
</script>

<style scoped lang="scss">
.collection-overview {
  width: 100%;
}

.panel-card,
.stat-card {
  border-radius: 12px;
}

.description-empty {
  color: #7f8b98;
  font-style: italic;
}

.overview-table :deep(th),
.overview-table :deep(td) {
  vertical-align: top;
}

.details-key {
  width: 170px;
  color: #758195;
  font-weight: 600;
}

.details-value {
  color: #1f2a37;
}

.edit-cell {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.readonly-cell {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.collection-color-display {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.collection-color-dot {
  width: 16px;
  height: 16px;
  border-radius: 999px;
  border: 1px solid rgba(0, 0, 0, 0.2);
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.9);
  flex: 0 0 auto;
}

.collection-color-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  color: #445066;
}

.description-row {
  align-items: flex-start;
}

.description-inline {
  white-space: pre-wrap;
  line-height: 1.5;
}

.statistics-header {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.statistics-subtitle {
  color: #758195;
  font-size: 0.86rem;
}

.stat-value {
  font-size: 1.8rem;
  line-height: 1;
  font-weight: 700;
  color: #1f2a37;
}

.stat-helper {
  margin-top: 8px;
  color: #758195;
  font-size: 0.82rem;
}
</style>
