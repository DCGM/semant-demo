<template>
  <q-card flat class="right-panel-menu">
    <q-card-section class="right-panel-menu-section">
      <div class="row items-center justify-between q-mb-md">
        <div class="text-subtitle1 text-weight-bold">
          Choose tags to be annotated
        </div>
        <div class="row items-center q-gutter-xs">
          <q-btn
            flat
            dense
            size="sm"
            label="Select all"
            :disable="isLoading || selectableTags.length === 0"
            @click="selectAll"
          />
          <q-btn
            flat
            dense
            size="sm"
            label="Deselect all"
            :disable="isLoading || selectedTagIds.length === 0"
            @click="deselectAll"
          />
          <q-btn flat round dense icon="close" @click="onClose">
            <q-tooltip>Close suggestions</q-tooltip>
          </q-btn>
        </div>
      </div>

      <div v-if="selectableTags.length" class="tag-catalog">
        <div
          v-for="tag in selectableTags"
          :key="tag.tagUuid"
          class="tag-catalog-item"
          :class="{ 'is-selected': isSelected(tag.tagUuid) }"
          role="checkbox"
          :aria-checked="isSelected(tag.tagUuid)"
          @click="toggleTag(tag.tagUuid)"
        >
          <q-icon
            :name="tag.tagPictogram"
            :style="{ color: tag.tagColor }"
            class="tag-catalog-icon"
          />
          <div class="tag-catalog-text">
            <div class="tag-catalog-name">{{ tag.tagName }}</div>
            <div
              v-if="tag.tagShorthand"
              class="tag-catalog-shorthand"
              :style="{ borderColor: tag.tagColor }"
            >
              {{ tag.tagShorthand }}
            </div>
          </div>
          <q-checkbox
            v-model="selectedTagIds"
            :val="tag.tagUuid"
            color="primary"
            class="tag-catalog-checkbox"
            :disable="isLoading"
            @click.stop
          />
        </div>
      </div>

      <div v-else class="text-caption text-grey-7">
        No tags available for suggestions.
        <div class="q-mt-sm q-ml-none">
          <go-to-tag-management
            :collectionId="props.collectionId"
            :before-redirect="onCancel"
          />
        </div>
      </div>

      <div
        v-if="isLoading"
        class="row items-center q-gutter-sm text-caption text-grey-8 q-mt-sm"
      >
        <q-spinner size="18px" color="primary" />
        <span>Generating suggestions...</span>
      </div>

      <q-banner
        v-else-if="noSuggestionsFound"
        inline-actions
        dense
        rounded
        class="bg-red-1 text-red-9 q-mt-md"
      >
        No suggestions were found for the selected tags.
      </q-banner>

      <q-separator class="q-my-md" />

      <div class="row justify-between items-center">
        <q-btn
          label="Cancel"
          color="grey-8"
          :disable="isLoading"
          @click="onCancel"
        />

        <q-btn
          color="primary"
          label="Start"
          icon="play_arrow"
          :loading="isLoading"
          :disable="selectedTagIds.length === 0 || isLoading"
          @click="onStart"
        />
      </div>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AvailableTag } from './ChunkTagAnnotator.vue'
import GoToTagManagement from './GoToTagManagement.vue'

const props = defineProps<{
  availableTags: AvailableTag[]
  isLoading?: boolean
  noSuggestionsFound?: boolean
  collectionId: string
}>()

const isLoading = computed(() => !!props.isLoading)
const noSuggestionsFound = computed(() => !!props.noSuggestionsFound)

const emit = defineEmits<{
  startSuggestions: [selectedTagIds: string[]]
  cancelSuggestions: []
  close: []
}>()

const selectedTagIds = ref<string[]>([])

const selectableTags = computed(() => {
  return props.availableTags.filter(
    (tag): tag is AvailableTag & { tagUuid: string } => tag.tagUuid !== null
  )
})

const isSelected = (tagId: string) => selectedTagIds.value.includes(tagId)

const toggleTag = (tagId: string) => {
  if (isLoading.value) return

  if (isSelected(tagId)) {
    selectedTagIds.value = selectedTagIds.value.filter((id) => id !== tagId)
  } else {
    selectedTagIds.value = [...selectedTagIds.value, tagId]
  }
}

const selectAll = () => {
  if (isLoading.value) return
  selectedTagIds.value = selectableTags.value.map((tag) => tag.tagUuid)
}

const deselectAll = () => {
  if (isLoading.value) return
  selectedTagIds.value = []
}

const onStart = () => {
  emit('startSuggestions', [...selectedTagIds.value])
}

const onCancel = () => {
  emit('cancelSuggestions')
}

const onClose = () => {
  emit('close')
}
</script>

<style scoped>
.tag-catalog {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tag-catalog-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 10px;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
  cursor: pointer;
}

.tag-catalog-item.is-selected {
  border-color: #1976d2;
  background: #f5f9ff;
}

.tag-catalog-icon {
  font-size: 18px;
}

.tag-catalog-text {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1 1 auto;
}

.tag-catalog-name {
  font-size: 0.95rem;
  color: #1a1a1a;
}

.tag-catalog-shorthand {
  border: 1px solid #d6d6d6;
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 0.8rem;
  color: #4a4a4a;
  background: #fafafa;
}

.tag-catalog-checkbox {
  margin-left: auto;
}
</style>
