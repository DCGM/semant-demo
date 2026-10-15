<template>
  <div class="chat-sources column q-gutter-y-sm" data-testid="chat-sources">
    <div v-if="question" class="chat-sources__question text-caption text-grey-8">
      Sources of the answer to <q class="text-weight-medium">{{ question }}</q>
    </div>

    <ol class="chat-sources__list">
      <li
        v-for="(source, index) in sources"
        :key="`${index}-${source.id}`"
        class="chat-sources__item"
        :class="{ 'chat-sources__item--selected': index === selectedIndex }"
        :aria-current="index === selectedIndex ? 'true' : undefined"
        :aria-label="`Source doc ${index + 1}`"
        :data-source-index="index"
      >
        <div class="row items-baseline no-wrap q-gutter-x-sm">
          <span class="chat-sources__number text-caption text-weight-bold">doc {{ index + 1 }}</span>
          <div class="col">
            <div class="text-body2 text-weight-medium chat-sources__title">
              {{ source.documentObject?.title || source.title || 'Untitled document' }}
            </div>
            <div class="text-caption text-grey-8">{{ details(source) }}</div>
          </div>
        </div>
        <div class="chat-sources__excerpt text-body2">{{ source.text }}</div>
        <div class="row items-center justify-between q-mt-xs">
          <q-btn
            dense
            flat
            no-caps
            color="primary"
            icon="menu_book"
            label="View in document"
            :aria-label="`View source doc ${index + 1} in its document`"
            class="chat-sources__view"
            @click="emit('view', index)"
          />
          <OriginalSourceLink :document="source.documentObject" :page-id="source.startPageId" class="text-caption" />
        </div>
      </li>
    </ol>
  </div>
</template>

<script setup lang="ts">
import { QBtn } from 'quasar'
import type { SearchResultChunk } from 'src/generated/api'
import OriginalSourceLink from 'src/features/documents/OriginalSourceLink.vue'

/** The sources of one chat assistant answer, numbered as its `[doc N]` citations. */
withDefaults(defineProps<{
  sources: SearchResultChunk[]
  /** The source open in its document, if any. */
  selectedIndex?: number | null
  /** The question the answer replied to, to tell answers apart. */
  question?: string | null
}>(), { selectedIndex: null, question: null })

const emit = defineEmits<{
  /** Show the source with this index in its document. */
  view: [index: number]
}>()

function details (source: SearchResultChunk): string {
  const year = source.documentObject?.yearIssued
  const pages = source.fromPage === source.toPage ? `page ${source.fromPage}` : `pages ${source.fromPage}–${source.toPage}`
  return [year ? String(year) : 'Year N/A', pages].join(' · ')
}
</script>

<style scoped>
.chat-sources__question {
  overflow-wrap: anywhere;
}

.chat-sources__list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.chat-sources__item {
  padding: 8px;
  border-left: 3px solid transparent;
  border-radius: 2px;
}

.chat-sources__item + .chat-sources__item {
  border-top: 1px solid rgba(0, 0, 0, 0.08);
}

.chat-sources__item--selected {
  border-left-color: var(--q-primary);
  background-color: #fff8d6;
}

.chat-sources__number {
  color: var(--q-primary);
  white-space: nowrap;
}

.chat-sources__title {
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.chat-sources__excerpt {
  margin-top: 4px;
  color: #333;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 6;
  line-clamp: 6;
  overflow: hidden;
}

.chat-sources__view {
  margin-left: -6px;
}
</style>
