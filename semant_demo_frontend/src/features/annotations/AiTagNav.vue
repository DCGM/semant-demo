<template>
  <!-- Previous / next pending AI suggestion of one tag, with "position/count". -->
  <div class="ai-tag-nav">
    <q-btn flat dense round size="xs" icon="chevron_left" @click="emit('prev')">
      <q-tooltip>Previous suggestion</q-tooltip>
    </q-btn>
    <span class="ai-tag-nav-counter">{{ index != null ? index + 1 : '–' }}/{{ count }}</span>
    <q-btn flat dense round size="xs" icon="chevron_right" @click="emit('next')">
      <q-tooltip>Next suggestion</q-tooltip>
    </q-btn>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  /** The tag's pending suggestions (at least one). */
  count: number
  /** The suggestion last reached, or null. */
  index: number | null
}>()

const emit = defineEmits<{ prev: [], next: [] }>()
</script>

<style scoped>
.ai-tag-nav {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  color: rgba(71, 85, 105, 0.85);
}

.ai-tag-nav-counter {
  font-size: 0.75rem;
  font-variant-numeric: tabular-nums;
  min-width: 28px;
  text-align: center;
  color: rgba(71, 85, 105, 0.85);
}
</style>
