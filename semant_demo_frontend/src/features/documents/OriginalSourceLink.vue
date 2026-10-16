<template>
  <!-- An external link to the original digitized document; nothing without a trustworthy
       URL (#255). semANT's own document and context navigation stays separate. -->
  <a
    v-if="url"
    :href="url"
    target="_blank"
    rel="noopener noreferrer"
    class="original-source-link text-primary"
    :aria-label="`${label} (${library}, opens in a new tab)`"
    :title="`Open the original in digitalniknihovna.cz (${library}) in a new tab`"
    data-testid="original-source-link"
  ><q-icon name="open_in_new" size="1.1em" class="q-mr-xs" />{{ label }}</a>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { QIcon } from 'quasar'
import { originalSourceUrl, type SourceDocument } from './originalSource'

const props = withDefaults(defineProps<{
  document: SourceDocument | null | undefined
  /** Opens the original at this page (a chunk's `startPageId`). */
  pageId?: string | null
  label?: string
}>(), { pageId: null, label: 'View in digital library' })

const url = computed(() => originalSourceUrl(props.document, props.pageId))
const library = computed(() => props.document?.library?.trim().toUpperCase() ?? '')
</script>

<style scoped>
.original-source-link {
  display: inline-flex;
  align-items: center;
  text-decoration: none;
  white-space: nowrap;
}

.original-source-link:hover,
.original-source-link:focus-visible {
  text-decoration: underline;
}
</style>
