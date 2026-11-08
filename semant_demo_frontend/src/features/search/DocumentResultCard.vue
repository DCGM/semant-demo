<template>
  <!-- A document of Explore's Documents results (#606): its metadata, opened in the shared
       document reader with the way back to these results. -->
  <q-card flat bordered class="document-result bg-white">
    <q-card-section>
      <div class="row no-wrap items-start">
        <router-link
          :to="documentLink(document.id, { from: 'search' })"
          class="col document-result__title text-h6 text-primary"
          :aria-label="`Open document ${number}: ${title}`"
          data-testid="document-result-open"
        >{{ number }}. {{ title }}</router-link>
      </div>
      <div v-if="document.subtitle" class="text-body2 text-grey-8 document-result__wrap">{{ document.subtitle }}</div>
      <div class="document-result__meta row text-caption text-grey-8">
        <div><q-icon name="person" class="q-mr-xs" />{{ document.author?.join(', ') || 'Unknown author' }}</div>
        <div data-testid="document-result-year"><q-icon name="event" class="q-mr-xs" />{{ document.yearIssued ?? 'Year unknown' }}</div>
        <div v-if="document.publisher"><q-icon name="business" class="q-mr-xs" />{{ document.publisher }}</div>
        <div v-if="document.language"><q-icon name="language" class="q-mr-xs" />{{ document.language }}</div>
        <div v-if="document.documentType"><q-icon name="category" class="q-mr-xs" />{{ document.documentType }}</div>
      </div>
      <div class="document-result__links text-caption">
        <OriginalSourceLink :document="document" />
      </div>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { QCard, QCardSection, QIcon } from 'quasar'
import type { Document } from 'src/generated/api'
import OriginalSourceLink from 'src/features/documents/OriginalSourceLink.vue'
import { documentLink } from 'src/features/documents/workspace/documentLink'

const props = defineProps<{
  document: Document
  /** 1-based position in the whole result list. */
  number: number
}>()

const title = computed(() => props.document.title?.trim() || 'Untitled document')
</script>

<style scoped>
.document-result__title {
  min-width: 0;
  line-height: 1.25;
  overflow-wrap: anywhere;
  text-decoration: none;
}

.document-result__title:hover,
.document-result__title:focus-visible {
  text-decoration: underline;
}

.document-result__wrap {
  overflow-wrap: anywhere;
}

.document-result__meta {
  gap: 2px 16px;
  margin-top: 4px;
  overflow-wrap: anywhere;
}

.document-result__links {
  margin-top: 6px;
}

.document-result__links:empty {
  display: none;
}
</style>
