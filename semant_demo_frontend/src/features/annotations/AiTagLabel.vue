<template>
  <!-- A tag's pictogram and name, as the AI Tagging panel lists its tags. -->
  <span class="ai-tag-row">
    <q-icon
      :name="tag.pictogram || 'label'"
      :style="{ color: tag.color || '#64748b' }"
      size="16px"
      class="q-mr-xs"
    />
    <span class="ai-tag-name">{{ tag.name }}</span>
  </span>
</template>

<script setup lang="ts">
import type { Tag } from 'src/generated/api'

defineProps<{ tag: Tag }>()
</script>

<style scoped>
.ai-tag-row {
  display: inline-flex;
  align-items: center;
  font-size: 0.9rem;
}

.ai-tag-name {
  color: rgba(15, 23, 42, 0.9);
}
</style>
