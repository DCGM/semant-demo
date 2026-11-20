<template>
  <!-- A tile: a corner badge only when there are unresolved suggestions. -->
  <q-badge
    v-if="badge"
    v-show="!!count"
    floating
    color="deep-purple-1"
    text-color="deep-purple-9"
    class="pending-suggestions-badge"
    role="img"
    :aria-label="label"
    data-testid="pending-suggestions"
  >
    <q-icon name="auto_awesome" size="12px" class="q-mr-xs" aria-hidden="true" />{{ count }}
    <q-tooltip>{{ label }}</q-tooltip>
  </q-badge>
  <!-- A table cell: the number, nothing for none. -->
  <span v-else data-testid="pending-suggestions">
    <template v-if="failed">
      –
      <q-tooltip>Could not be counted</q-tooltip>
    </template>
    <template v-else-if="count">{{ count }}</template>
  </span>
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue'
import { plural } from 'src/shared/plural'
import { useCollectionStats } from './useCollectionStats'

// A collection's unresolved AI suggestions on the Collections page (#770), from its
// statistics: the cache the Overview tab shares, and a read that leaves the collection's
// annotation store's recorded use alone. Only the shown tiles or rows ask for them.
const props = defineProps<{
  collectionId: string
  /** As a tile's badge (hidden for none and when it could not be counted), else a table cell's number. */
  badge?: boolean
}>()

const stats = useCollectionStats(toRef(props, 'collectionId'), computed(() => true))
const count = computed(() => stats.data.value?.suggestionsCount)
const failed = stats.isError
const label = computed(() => `${plural(count.value ?? 0, 'AI suggestion')} not yet confirmed or rejected`)
</script>

<style scoped>
.pending-suggestions-badge {
  border: 1px solid rgba(94, 53, 177, 0.3);
  padding: 3px 6px;
}
</style>
