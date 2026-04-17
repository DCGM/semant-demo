<template>
  <q-card class="suggestions-card bg-grey-2 q-mt-md">
    <q-card-section class="row items-center justify-between">
      <div class="text-subtitle1 text-weight-bold">
        Choose tags to be annotated
      </div>
    </q-card-section>

    <q-separator />

    <q-card-section>
      <q-option-group
        v-model="selectedTagIds"
        :options="tagOptions"
        type="checkbox"
        color="primary"
      />

      <div v-if="tagOptions.length === 0" class="text-caption text-grey-7">
        No tags available for suggestions.
      </div>
    </q-card-section>

    <q-card-actions class="q-pa-md bg-grey-3 row justify-between items-center">
      <q-btn flat label="Cancel" color="grey-8" @click="onCancel" />

      <q-btn
        color="primary"
        label="Start"
        icon="play_arrow"
        :disable="selectedTagIds.length === 0"
        @click="onStart"
      />
    </q-card-actions>
  </q-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AvailableTag } from './ChunkTagAnnotator.vue'

const props = defineProps<{
  availableTags: AvailableTag[]
}>()

const emit = defineEmits<{
  startSuggestions: [selectedTagIds: string[]]
  cancelSuggestions: []
}>()

const selectedTagIds = ref<string[]>([])

const tagOptions = computed(() => {
  return props.availableTags
    .filter((tag) => tag.tagUuid !== null)
    .map((tag) => ({
      label: tag.tagName,
      value: tag.tagUuid as string
    }))
})

const onStart = () => {
  emit('startSuggestions', [...selectedTagIds.value])
}

const onCancel = () => {
  emit('cancelSuggestions')
}
</script>

<style scoped>
.suggestions-card {
  position: sticky;
  /* top: calc(64px + 360px); */
}
</style>
