<template>
  <q-card class="suggestions-card bg-grey-2 q-mt-md">
    <q-card-section class="row items-center justify-between">
      <div class="text-subtitle1 text-weight-bold">
        Automatic Annotation Suggestions
      </div>
      <q-btn
        dense
        color="primary"
        :label="showOptions ? 'Hide options' : 'Open options'"
        :icon="showOptions ? 'expand_less' : 'expand_more'"
        @click="showOptions = !showOptions"
      />
    </q-card-section>

    <q-slide-transition>
      <div v-show="showOptions">
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

        <q-card-actions align="right" class="q-pa-md bg-grey-3">
          <q-btn
            color="primary"
            label="Start"
            icon="play_arrow"
            :disable="selectedTagIds.length === 0"
            @click="onStart"
          />
        </q-card-actions>
      </div>
    </q-slide-transition>
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
}>()

const showOptions = ref(false)
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
</script>

<style scoped>
.suggestions-card {
  position: sticky;
  top: calc(64px + 360px);
}
</style>
