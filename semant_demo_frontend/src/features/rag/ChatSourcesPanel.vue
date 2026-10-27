<template>
  <div class="chat-sources" data-testid="chat-sources">
    <ol class="chat-sources__list">
      <li
        v-for="entry in entries"
        :key="entry.id"
        :ref="el => setItemEl(entry.id, el as HTMLElement | null)"
        class="chat-sources__item"
        :class="{ 'chat-sources__item--selected': entry.id === selectedId }"
        :aria-current="entry.id === selectedId ? 'true' : undefined"
        :aria-label="`Source ${entry.label}`"
        :data-source-id="entry.id"
      >
        <!-- One click selects (and expands) the source, a double click opens its document
             (a web search result has none). -->
        <div
          class="chat-sources__summary"
          role="button"
          tabindex="0"
          :aria-expanded="entry.id === selectedId ? 'true' : 'false'"
          @click="emit('select', entry.id)"
          @dblclick="hasDocument(entry.source) && emit('open', entry.id)"
          @keydown.enter.prevent="emit('select', entry.id)"
          @keydown.space.prevent="emit('select', entry.id)"
        >
          <div class="row items-baseline no-wrap q-gutter-x-sm">
            <span class="chat-sources__label text-caption text-weight-bold">{{ entry.label }}</span>
            <div class="col">
              <div class="text-body2 text-weight-medium chat-sources__title">
                {{ entry.source.documentObject?.title || entry.source.title || 'Untitled document' }}
              </div>
              <div class="text-caption text-grey-8">{{ details(entry.source) }}</div>
            </div>
          </div>
          <div
            class="chat-sources__text text-body2"
            :class="{ 'chat-sources__text--collapsed': entry.id !== selectedId }"
            data-testid="chat-source-text"
          >{{ entry.source.text }}</div>
        </div>
        <div class="row items-center justify-between q-mt-xs">
          <q-btn
            v-if="hasDocument(entry.source)"
            dense
            flat
            no-caps
            color="primary"
            icon="menu_book"
            label="View document"
            :aria-label="`View source ${entry.label} in its document`"
            class="chat-sources__view"
            @click="emit('open', entry.id)"
          />
          <span v-else class="text-caption text-grey-8" data-testid="chat-source-web">Web search result, not in the corpus</span>
          <OriginalSourceLink :document="entry.source.documentObject" :page-id="entry.source.startPageId" class="text-caption" />
        </div>
      </li>
    </ol>
  </div>
</template>

<script setup lang="ts">
import { nextTick, watch } from 'vue'
import { QBtn } from 'quasar'
import type { SearchResultChunk } from 'src/generated/api'
import OriginalSourceLink from 'src/features/documents/OriginalSourceLink.vue'
import { hasDocument, type ChatSourceEntry } from './useChatSources'

/**
 * The sources of a whole chat conversation, labelled as their citations (`S1`, `S2`...).
 * Only the selected source is expanded to its full stored text.
 */
const props = withDefaults(defineProps<{
  entries: ChatSourceEntry[]
  selectedId?: string | null
  /** Brings the named source into view whenever it changes. */
  reveal?: { id: string, seq: number } | null
}>(), { selectedId: null, reveal: null })

const emit = defineEmits<{
  /** Select (and expand) the source. */
  select: [id: string]
  /** Show the source in its document. */
  open: [id: string]
}>()

function details (source: SearchResultChunk): string {
  if (!hasDocument(source)) return 'Web search'
  const year = source.documentObject?.yearIssued
  const pages = source.fromPage === source.toPage ? `page ${source.fromPage}` : `pages ${source.fromPage}–${source.toPage}`
  return [year ? String(year) : 'Year N/A', pages].join(' · ')
}

const itemEls = new Map<string, HTMLElement>()
function setItemEl (id: string, el: HTMLElement | null) {
  if (el) itemEls.set(id, el)
  else itemEls.delete(id)
}

/** The nearest scrolling ancestor; the page itself is never scrolled for the list. */
function scroller (el: HTMLElement): HTMLElement | null {
  for (let parent = el.parentElement; parent; parent = parent.parentElement) {
    const overflow = getComputedStyle(parent).overflowY
    if ((overflow === 'auto' || overflow === 'scroll') && parent.scrollHeight > parent.clientHeight) return parent
  }
  return null
}

watch(() => props.reveal, async (reveal) => {
  if (!reveal) return
  await nextTick() // the selected source expands first
  const el = itemEls.get(reveal.id)
  const container = el && scroller(el)
  if (!el || !container) return
  const box = el.getBoundingClientRect()
  const view = container.getBoundingClientRect()
  if (box.top < view.top) {
    container.scrollTop -= view.top - box.top + 8
  } else if (box.bottom > view.bottom) {
    // A source taller than the view shows from its start.
    container.scrollTop += Math.min(box.bottom - view.bottom + 8, box.top - view.top - 8)
  }
})
</script>

<style scoped>
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

.chat-sources__summary {
  cursor: pointer;
  outline-offset: 2px;
}

.chat-sources__label {
  color: var(--q-primary);
  white-space: nowrap;
}

.chat-sources__title {
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.chat-sources__text {
  margin-top: 4px;
  color: #333;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.chat-sources__text--collapsed {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  overflow: hidden;
}

.chat-sources__view {
  margin-left: -6px;
}
</style>
