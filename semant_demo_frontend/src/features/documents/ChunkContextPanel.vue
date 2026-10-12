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
        </div>
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
            :aria-label="chunk.id === targetChunkId ? 'Matched passage' : undefined"
            :data-chunk-id="chunk.id"
          >
            <div class="chunk-context__chunk-text text-body2">{{ chunk.text }}</div>
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
import type { ContextDirection } from './useChunkContext'

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
  emptyText?: string
}>(), {
  hasBefore: false,
  hasAfter: false,
  focusRequest: 0,
  loading: false,
  extending: null,
  error: null,
  returnLabel: null,
  emptyText: 'Nothing selected.'
})

const emit = defineEmits<{
  extend: [direction: ContextDirection]
  /** Load the passage around the target again (retry). */
  reload: []
  return: []
}>()

const targetLoaded = computed(() => props.chunks.some(c => c.id === props.targetChunkId))

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
