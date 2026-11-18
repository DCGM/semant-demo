<template>
  <!-- A tile: a badge only when there are unresolved suggestions. -->
  <q-badge
    v-if="badge"
    v-show="!!count"
    color="deep-purple-1"
    text-color="deep-purple-9"
    class="pending-suggestions-badge"
    data-testid="pending-suggestions"
  >
    <q-icon name="auto_awesome" size="12px" class="q-mr-xs" />
    {{ count ? plural(count, 'AI suggestion') : '' }}
    <q-tooltip>AI suggestions not yet confirmed or rejected</q-tooltip>
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
import { toRef } from 'vue'
import { plural } from 'src/shared/plural'
import { usePendingSuggestions } from './usePendingSuggestions'

// A collection's unresolved AI suggestions on the Collections page (#770).
const props = defineProps<{
  collectionId: string
  /** As a tile's badge (hidden for none and when it could not be counted), else a table cell's number. */
  badge?: boolean
}>()

const { count, failed } = usePendingSuggestions(toRef(props, 'collectionId'))
</script>
