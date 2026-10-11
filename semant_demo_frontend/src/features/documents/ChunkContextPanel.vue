<template>
  <div class="chunk-context column q-gutter-y-sm" data-testid="chunk-context">
    <div v-if="!targetChunkId" class="text-caption text-grey-7">
      {{ emptyText }}
    </div>

    <template v-else>
      <div v-if="document" class="chunk-context__document" data-testid="chunk-context-document">
        <div class="text-subtitle2 text-weight-medium chunk-context__title">{{ documentTitle }}</div>
        <div class="text-caption text-grey-8">
          <span v-if="document.author?.length">{{ document.author.join(', ') }} · </span>
          <span>{{ document.yearIssued || 'Year N/A' }}</span>
          <span v-if="document.publisher"> · {{ document.publisher }}</span>
        </div>
        <div v-if="targetChunk" class="text-caption text-grey-8" data-testid="chunk-context-position">
          Passage {{ positionLabel }} · Pages {{ targetChunk.fromPage }}–{{ targetChunk.toPage }}
        </div>
      </div>

      <div class="row q-gutter-xs">
        <q-btn
          v-if="returnLabel"
          dense
          flat
          no-caps
          color="primary"
          icon="arrow_back"
          :label="returnLabel"
          @click="emit('return')"
        />
        <q-btn
          dense
          flat
          no-caps
          color="primary"
          icon="my_location"
          label="Jump to match"
          :disable="loading"
          @click="jumpToTarget"
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
            :tabindex="chunk.id === targetChunkId ? -1 : undefined"
            :data-chunk-id="chunk.id"
          >
            <div class="chunk-context__pages text-caption text-grey-7">
              <span v-if="chunk.id === targetChunkId" class="chunk-context__match-label">Match · </span>
              Pages {{ chunk.fromPage }}–{{ chunk.toPage }}
            </div>
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
import { computed, nextTick, watch } from 'vue'
import { QBtn, QSpinner } from 'quasar'
import type { Document, TextChunk } from 'src/generated/api'
import type { ContextDirection } from './useChunkContext'

const props = withDefaults(defineProps<{
  /** The chunk to highlight; null shows `emptyText`. */
  targetChunkId: string | null
  document: Document | null
  /** The loaded passage, in document order. */
  chunks: TextChunk[]
  hasBefore?: boolean
  hasAfter?: boolean
  totalChunks?: number | null
  loading?: boolean
  extending?: ContextDirection | null
  error?: string | null
  /** Label of the action returning to where the target came from (e.g. a search result). */
  returnLabel?: string | null
  emptyText?: string
}>(), {
  hasBefore: false,
  hasAfter: false,
  totalChunks: null,
  loading: false,
  extending: null,
  error: null,
  returnLabel: null,
  emptyText: 'Nothing selected.'
})

const emit = defineEmits<{
  extend: [direction: ContextDirection]
  /** Load the passage around the target again (retry, or the target was dropped). */
  reload: []
  return: []
}>()

const targetChunk = computed(() => props.chunks.find(c => c.id === props.targetChunkId) ?? null)

const documentTitle = computed(() => {
  const d = props.document
  if (!d) return ''
  const part = [d.partNumber, d.partName].filter(v => v !== null && v !== undefined && v !== '').join(' ')
  return [d.title || 'Untitled document', d.subtitle, part].filter(Boolean).join(' – ')
})

const positionLabel = computed(() => {
  const order = targetChunk.value?.order
  if (order === null || order === undefined) return '?'
  return props.totalChunks ? `${order + 1} of ${props.totalChunks}` : `${order + 1}`
})

// Chunk elements by id, to bring the target into view.
const chunkEls = new Map<string, HTMLElement>()
function setChunkEl (id: string, el: HTMLElement | null) {
  if (el) chunkEls.set(id, el)
  else chunkEls.delete(id)
}

// Set when a new target is shown or "Jump to match" had to reload it: the target is
// scrolled into view as soon as it is loaded.
let scrollPending = true

function scrollToTarget (focus: boolean) {
  const el = props.targetChunkId ? chunkEls.get(props.targetChunkId) : undefined
  if (!el) return false
  el.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  if (focus) el.focus({ preventScroll: true })
  return true
}

function jumpToTarget () {
  if (scrollToTarget(true)) return
  // Not loaded (dropped while reading further): read the passage around it again.
  scrollPending = true
  emit('reload')
}

watch(() => props.targetChunkId, () => { scrollPending = true })

watch(() => [props.loading, targetChunk.value] as const, async ([loading, chunk]) => {
  if (loading || !chunk || !scrollPending) return
  await nextTick()
  if (scrollToTarget(false)) scrollPending = false
}, { immediate: true })
</script>

<style scoped>
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
  outline: none;
}

.chunk-context__chunk--target:focus-visible {
  outline: 2px solid var(--q-primary);
  outline-offset: 1px;
}

.chunk-context__match-label {
  color: var(--q-primary);
  font-weight: 500;
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
