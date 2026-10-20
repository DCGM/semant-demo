<template>
  <div class="column q-gutter-y-md document-summary-panel">
    <q-btn
      v-if="!loading"
      color="secondary"
      icon="auto_awesome"
      label="Summarize Document"
      @click="emit('summarize')"
    />
    <div v-else class="row items-center q-gutter-sm">
      <q-spinner color="primary" size="1.2em" />
      <span class="text-body2">Summarizing the document…</span>
      <q-space />
      <q-btn
        flat dense no-caps
        size="sm"
        color="negative"
        icon="stop"
        label="Cancel"
        @click="emit('cancel')"
      />
    </div>

    <q-select
      :model-value="length"
      @update:model-value="emit('update:length', $event)"
      :options="SUMMARY_LENGTH_OPTIONS"
      label="Length"
      dense
      outlined
      emit-value
      map-options
      data-testid="document-summary-length"
    />

    <div v-if="error" class="text-negative text-body2" role="alert">{{ error }}</div>

    <q-card v-if="tokens.length" flat bordered class="bg-blue-grey-1" data-testid="document-summary">
      <q-card-section>
        <div class="text-caption text-grey q-mb-sm">Time spent: {{ timeSpent.toFixed(2) }}s</div>
        <div
          v-if="truncated"
          class="text-caption text-warning q-mb-sm"
          role="status"
          data-testid="document-summary-truncated"
        >
          <q-icon name="warning" size="16px" class="q-mr-xs" />
          Partial summary — first {{ summarizedChunks }} of {{ totalChunks }} chunks.
        </div>
        <CitedSummaryText
          :tokens="tokens"
          :label="(citation) => citation.number"
          @cite="(citation) => emit('cite', citation.chunkId, citation.order)"
        />
      </q-card-section>
    </q-card>
    <div v-else-if="!error && !loading" class="text-caption text-grey-7">
      Summarize the document to get an overview with citations of its source passages.
    </div>
  </div>
</template>

<script setup lang="ts">
import type { SummaryLength } from 'src/generated/api'
import CitedSummaryText from 'src/shared/ui/CitedSummaryText.vue'
import { SUMMARY_LENGTH_OPTIONS } from 'src/shared/summaryLength'
import type { SummaryToken } from './useDocumentSummary'

// Props-in/events-out only: this panel does not know it is shown in a sidebar and has no
// direct store/API access, matching docs/RIGHT_SIDEBAR.md section 3. The enclosing page
// (DocumentViewLayout) owns the useDocumentSummary() composable and passes its state here.
withDefaults(defineProps<{
  tokens: SummaryToken[]
  timeSpent: number
  length: SummaryLength
  truncated?: boolean
  summarizedChunks?: number
  totalChunks?: number
  error?: string | null
  loading?: boolean
}>(), { truncated: false, summarizedChunks: 0, totalChunks: 0, error: null, loading: false })

const emit = defineEmits<{
  summarize: []
  cancel: []
  cite: [chunkId: string, order: number | null]
  'update:length': [value: SummaryLength]
}>()
</script>

<style scoped>
/* Quasar's .column utility wraps by default: inside a `fill` RightSidebarPanel (a bounded
   height, not auto), a summary longer than the panel's height would otherwise wrap sideways
   into a second flex column next to the button instead of overflowing below it. Disabling
   wrap, and letting the card scroll on its own, keeps Summarize/Cancel fixed in view while
   the summary scrolls underneath it, matching the "fill" contract documented where this
   panel is registered (DocumentViewLayout.vue). */
.document-summary-panel {
  flex-wrap: nowrap;
}

.document-summary-panel > .q-card {
  /* flex-grow: 0, not 1 — the card should size to its content (a short summary keeps the
     original compact look) and only shrink below that, scrolling internally, when a long
     one would otherwise overflow the panel's bounded ("fill") height. */
  flex: 0 1 auto;
  min-height: 0;
  overflow-y: auto;
}
</style>
