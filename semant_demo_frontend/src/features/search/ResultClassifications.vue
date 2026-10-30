<template>
  <WrappingBadges v-if="badges.length" :watch-key="badges" class="result-classifications q-mt-xs">
    <q-badge
      v-for="badge in badges"
      :key="badge.key"
      :color="badge.color.bg"
      :text-color="badge.color.text"
      class="classification-badge"
    >
      <span class="visually-hidden">{{ badge.category }}: </span>{{ badge.value }}
      <q-tooltip>{{ badge.category }}: {{ badge.value }}</q-tooltip>
    </q-badge>
  </WrappingBadges>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { SearchFilter } from 'src/generated/api'
import WrappingBadges from 'src/shared/ui/WrappingBadges.vue'
import { classificationBadges } from './classifications'

const props = withDefaults(defineProps<{
  metadata?: Record<string, string[]> | null
  filters: readonly SearchFilter[]
}>(), { metadata: null })

const badges = computed(() => classificationBadges(props.metadata, props.filters))
</script>

<style scoped>
.classification-badge {
  height: 20px;
  line-height: 16px;
  padding: 2px 6px;
  max-width: 100%;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
