<template>
  <!-- A document of Explore's Documents results (#606, #607): its metadata and, for a text query,
       why it matched and its best-matching passage, opened in the shared document reader (at
       that passage when there is one) with the way back to these results. -->
  <q-card flat bordered class="document-result bg-white">
    <q-card-section>
      <div class="row no-wrap items-start">
        <router-link
          :to="openLink"
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
      <div v-if="hit.match" class="document-result__match text-caption" data-testid="document-result-match">
        <q-icon :name="hit.match === 'metadata' ? 'menu_book' : 'format_quote'" class="q-mr-xs" />{{ matchLabel }}
      </div>
      <router-link
        v-if="hit.chunk"
        :to="documentLink(document.id, { chunkId: hit.chunk.id, from: 'search' })"
        class="document-result__evidence text-body2"
        :aria-label="`Open document ${number} at its best-matching passage`"
        data-testid="document-result-evidence"
      >{{ excerpt }}</router-link>
      <div class="document-result__links text-caption">
        <OriginalSourceLink :document="document" />
      </div>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { QCard, QCardSection, QIcon } from 'quasar'
import type { DocumentHit } from 'src/generated/api'
import OriginalSourceLink from 'src/features/documents/OriginalSourceLink.vue'
import { documentLink } from 'src/features/documents/workspace/documentLink'

const props = defineProps<{
  hit: DocumentHit
  /** 1-based position in the whole result list. */
  number: number
}>()

/** Characters of the best-matching passage shown; the reader shows all of it. */
const EXCERPT_LENGTH = 320

const document = computed(() => props.hit.document)
const title = computed(() => document.value.title?.trim() || 'Untitled document')
const openLink = computed(() => documentLink(document.value.id, { chunkId: props.hit.chunk?.id ?? null, from: 'search' }))
const matchLabel = computed(() => {
  if (props.hit.match === 'metadata') {
    return props.hit.chunk ? 'Matches the title, author or publisher; best passage:' : 'Matches the title, author or publisher'
  }
  return 'Best-matching passage:'
})
const excerpt = computed(() => {
  const text = props.hit.chunk?.text.trim() ?? ''
  return text.length > EXCERPT_LENGTH ? `${text.slice(0, EXCERPT_LENGTH).trimEnd()}…` : text
})
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

.document-result__match {
  margin-top: 8px;
  color: var(--q-primary);
}

.document-result__evidence {
  display: block;
  margin-top: 4px;
  padding-left: 12px;
  border-left: 3px solid var(--q-primary);
  color: inherit;
  text-decoration: none;
  overflow-wrap: anywhere;
}

.document-result__evidence:hover,
.document-result__evidence:focus-visible {
  text-decoration: underline;
}

.document-result__links {
  margin-top: 6px;
}

.document-result__links:empty {
  display: none;
}
</style>
