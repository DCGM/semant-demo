<template>
  <!-- A small text link on its own line, so it is not mistaken for the drawer's collapse
       button next to it (#479). Pages pass a fixed parent route, not browser history (#253). -->
  <!-- aria-label (e.g. "Back to collections") falls through to the link. -->
  <router-link :to="props.to" class="back-link">
    <q-icon name="arrow_back" size="14px" />
    <span>{{ props.label }}</span>
  </router-link>
</template>

<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'

const props = defineProps<{
  to: RouteLocationRaw
  /** Short name of the parent page shown next to the arrow. */
  label: string
}>()
</script>

<style scoped lang="scss">
.back-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 2px;
  font-size: 0.8rem;
  font-weight: 500;
  color: rgba(0, 0, 0, 0.6);
  text-decoration: none;
}

.back-link:hover {
  color: var(--q-primary);
  text-decoration: underline;
}
</style>
