<template>
  <div class="chunk-context column q-gutter-y-sm" data-testid="chunk-context">
    <div v-if="!targetChunkId" class="text-caption text-grey-7">
      {{ emptyText }}
    </div>

    <template v-else>
      <!-- Stays at the top of the sidebar's scroller while the text scrolls. -->
      <div ref="headerEl" class="chunk-context__header" data-testid="chunk-context-header">
        <div v-if="document" class="chunk-context__document">
          <div class="text-subtitle2 text-weight-medium chunk-context__title">{{ documentTitle }}</div>
          <div class="text-caption text-grey-8">{{ document.yearIssued || 'Year N/A' }}</div>
          <OriginalSourceLink :document="document" :page-id="targetPageId" class="text-caption" />
        </div>
        <slot name="header" />
        <q-btn
          v-if="returnLabel"
          dense
          flat
          no-caps
          color="primary"
          icon="center_focus_strong"
          :label="returnLabel"
          class="chunk-context__return"
          @click="emit('return')"
        />
      </div>

      <div v-if="error" class="text-negative text-body2 row items-center q-gutter-x-sm" role="alert">
        <span>{{ error }}</span>
        <q-btn v-if="!chunks.length" dense flat no-caps color="primary" label="Retry" @click="emit('reload')" />
      </div>

      <div v-if="loading" class="row items-center text-caption text-grey-7" aria-live="polite">
        <q-spinner color="primary" size="1.5em" class="q-mr-sm" />
        Loading the document…
      </div>

      <template v-else-if="chunks.length">
        <q-btn
          v-if="hasBefore"
          dense
          outline
          no-caps
          color="primary"
          icon="expand_less"
          label="Show earlier text"
          :loading="extending === 'before'"
          :disable="!!extending"
          @click="emit('extend', 'before')"
        />
        <div v-else class="chunk-context__edge text-caption text-grey-6">Start of document</div>

        <div class="chunk-context__text">
          <section
            v-for="chunk in chunks"
            :key="chunk.id"
            :ref="el => setChunkEl(chunk.id, el as HTMLElement | null)"
            class="chunk-context__chunk"
            :class="{ 'chunk-context__chunk--target': chunk.id === targetChunkId }"
            :aria-current="chunk.id === targetChunkId ? 'true' : undefined"
            :aria-label="chunk.id === targetChunkId ? (targetLabel ? `Cited passage ${targetLabel}` : targetName) : undefined"
            :data-chunk-id="chunk.id"
          >
            <div
              v-if="targetLabel && chunk.id === targetChunkId"
              class="chunk-context__target-label text-caption text-weight-bold"
              data-testid="chunk-context-target-label"
            >{{ targetLabel }}</div>
            <div class="chunk-context__chunk-text text-body2"><template
              v-for="(part, index) in textParts(chunk)"
              :key="index"
            ><mark
              v-if="part.marked"
              class="chunk-context__mark"
              data-testid="chunk-context-mark"
            >{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></div>
          </section>
        </div>

        <q-btn
          v-if="hasAfter"
          dense
          outline
          no-caps
          color="primary"
          icon="expand_more"
          label="Show later text"
          :loading="extending === 'after'"
          :disable="!!extending"
          @click="emit('extend', 'after')"
        />
        <div v-else class="chunk-context__edge text-caption text-grey-6">End of document</div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { QBtn, QSpinner } from 'quasar'
import type { Document, DocumentChunk } from 'src/generated/api'
import OriginalSourceLink from './OriginalSourceLink.vue'
import type { ContextDirection } from './useChunkContext'
import { projectSpan } from 'src/features/annotations/spanOffsets'

/** An exact range to mark: UTF-16 offsets on the chunk where it starts, possibly continuing
 * into the following chunks (span coordinates, `annotations/spanOffsets.ts`). */
export interface ContextHighlight {
  chunkId: string
  start: number
  end: number
}

const props = withDefaults(defineProps<{
  /** The chunk to highlight; null shows `emptyText`. */
  targetChunkId: string | null
  document: Document | null
  /** The loaded passage, in document order. */
  chunks: DocumentChunk[]
  hasBefore?: boolean
  hasAfter?: boolean
  /** Changes with every request to show the target (also the same one again): it is
   * scrolled into view as soon as it is loaded. */
  focusRequest?: number
  loading?: boolean
  extending?: ContextDirection | null
  error?: string | null
  /** Label of the action returning to where the target came from (e.g. a search result). */
  returnLabel?: string | null
  /** Reference shown with the highlighted target (e.g. a chat citation's `S3`); none by default. */
  targetLabel?: string | null
  /** Accessible name of the target chunk when it has no `targetLabel`. */
  targetName?: string
  /** A range marked in the text (an annotation); none by default. */
  highlight?: ContextHighlight | null
  emptyText?: string
}>(), {
  hasBefore: false,
  hasAfter: false,
  focusRequest: 0,
  loading: false,
  extending: null,
  error: null,
  returnLabel: null,
  targetLabel: null,
  targetName: 'Matched passage',
  highlight: null,
  emptyText: 'Nothing selected.'
})

const emit = defineEmits<{
  extend: [direction: ContextDirection]
  /** Load the passage around the target again (retry). */
  reload: []
  return: []
}>()

const targetLoaded = computed(() => props.chunks.some(c => c.id === props.targetChunkId))
// The original opens at the matched passage's first page. Remembered once the target is
// loaded: extending the passage can trim the target chunk away, not the page it is on.
const targetPageId = ref<string | null>(null)
watch(() => props.targetChunkId, () => { targetPageId.value = null })
watch(() => [props.targetChunkId, props.chunks] as const, ([id, chunks]) => {
  const page = chunks.find(c => c.id === id)?.startPageId
  if (page) targetPageId.value = page
}, { immediate: true })

// The highlight's part in each loaded chunk; it ends at a gap in chunk order.
const marked = computed(() => {
  const parts = new Map<string, { start: number, end: number }>()
  const h = props.highlight
  const anchor = h ? props.chunks.findIndex(c => c.id === h.chunkId) : -1
  if (!h || anchor < 0) return parts
  const ordered = props.chunks.map(c => ({ order: c.order ?? Number.NaN, text: c.text }))
  for (const part of projectSpan(ordered, anchor, h.start, h.end)) {
    parts.set(props.chunks[part.chunk].id, { start: part.start, end: part.end })
  }
  return parts
})

function textParts (chunk: DocumentChunk): { text: string, marked: boolean }[] {
  const part = marked.value.get(chunk.id)
  if (!part) return [{ text: chunk.text, marked: false }]
  return [
    { text: chunk.text.slice(0, part.start), marked: false },
    { text: chunk.text.slice(part.start, part.end), marked: true },
    { text: chunk.text.slice(part.end), marked: false }
  ].filter(p => p.text)
}

const documentTitle = computed(() => {
  const d = props.document
  if (!d) return ''
  const part = [d.partNumber, d.partName].filter(v => v !== null && v !== undefined && v !== '').join(' ')
  return [d.title || 'Untitled document', d.subtitle, part].filter(Boolean).join(' – ')
})

const headerEl = ref<HTMLElement | null>(null)

// Chunk elements by id, to bring the target into view.
const chunkEls = new Map<string, HTMLElement>()
function setChunkEl (id: string, el: HTMLElement | null) {
  if (el) chunkEls.set(id, el)
  else chunkEls.delete(id)
}

// Set by every request to show the target; cleared once it is in view.
let scrollPending = true
watch(() => props.focusRequest, () => { scrollPending = true })

watch(() => [props.focusRequest, props.loading, targetLoaded.value] as const, async ([, loading, loaded]) => {
  if (loading || !loaded || !scrollPending) return
  await nextTick()
  const el = props.targetChunkId ? chunkEls.get(props.targetChunkId) : undefined
  if (!el) return
  scrollPending = false
  // Clear of the sticky header; a match taller than half the screen shows from its start.
  el.style.scrollMarginTop = `${(headerEl.value?.offsetHeight ?? 0) + 8}px`
  const tall = el.getBoundingClientRect().height > window.innerHeight / 2
  el.scrollIntoView?.({ behavior: 'smooth', block: tall ? 'start' : 'center' })
}, { immediate: true })
</script>

<style scoped>
.chunk-context__header {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 8px 0 4px;
  background: #fff;
  border-bottom: 1px solid rgba(0, 0, 0, 0.12);
}

.chunk-context__return {
  margin-left: -6px;
}

.chunk-context__title {
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.chunk-context__text {
  /* Lets the browser keep the reading position when earlier text is added above. */
  overflow-anchor: auto;
}

.chunk-context__chunk {
  padding: 6px 8px;
  border-left: 3px solid transparent;
  border-radius: 2px;
}

.chunk-context__chunk + .chunk-context__chunk {
  margin-top: 4px;
}

.chunk-context__chunk--target {
  border-left-color: var(--q-primary);
  background-color: #fff8d6;
}

.chunk-context__mark {
  background-color: #ffd54f;
  color: inherit;
  border-radius: 2px;
  box-shadow: 0 0 0 1px #c49000;
}

.chunk-context__target-label {
  color: var(--q-primary);
  line-height: 1.2;
}

.chunk-context__chunk-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: #333;
}

.chunk-context__edge {
  text-align: center;
  font-style: italic;
}
</style>
