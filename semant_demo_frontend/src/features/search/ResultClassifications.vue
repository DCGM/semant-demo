<template>
  <div v-if="rows.length" class="result-classifications text-caption text-grey-8 q-mt-xs">
    <div v-for="row in shownRows" :key="row.key" class="classification-row">
      <strong>{{ row.label }}:</strong> {{ row.values.join(', ') }}
    </div>
    <q-btn
      v-if="rows.length > previewCount"
      flat
      dense
      no-caps
      size="sm"
      color="primary"
      class="q-px-none"
      :label="expanded ? 'Show less' : `Show more (${rows.length - previewCount})`"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { SearchFilter } from 'src/generated/api'
import { classificationRows } from './classifications'

const props = withDefaults(defineProps<{
  metadata?: Record<string, string[]> | null
  filters: readonly SearchFilter[]
  previewCount?: number
}>(), { metadata: null, previewCount: 3 })

// Local to this result; never part of the search or filter state.
const expanded = ref(false)

const rows = computed(() => classificationRows(props.metadata, props.filters))
const shownRows = computed(() => expanded.value ? rows.value : rows.value.slice(0, props.previewCount))
</script>

<style scoped>
.classification-row {
  overflow-wrap: anywhere;
}
</style>
