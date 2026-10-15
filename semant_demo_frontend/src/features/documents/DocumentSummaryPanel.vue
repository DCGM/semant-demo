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

    <div v-if="error" class="text-negative text-body2" role="alert">{{ error }}</div>

    <q-card v-if="tokens.length" flat bordered class="bg-blue-grey-1" data-testid="document-summary">
      <q-card-section>
        <div class="text-caption text-grey q-mb-sm">Time spent: {{ timeSpent.toFixed(2) }}s</div>
        <div class="text-body2" style="white-space: pre-wrap;">
          <template v-for="(token, idx) in tokens" :key="idx">
            <span v-if="token.type === 'text'">{{ token.value }}</span>
            <a
              v-else
              href="#"
              class="citation-link"
              @click.prevent="emit('cite', token.chunkId)"
            >[{{ token.number }}]</a>
          </template>
        </div>
      </q-card-section>
    </q-card>
    <div v-else-if="!error && !loading" class="text-caption text-grey-7">
      Summarize the document to get an overview with citations of its source passages.
    </div>
  </div>
</template>

<script setup lang="ts">
import type { SummaryToken } from './useDocumentSummary'

// Props-in/events-out only: this panel does not know it is shown in a sidebar and has no
// direct store/API access, matching docs/RIGHT_SIDEBAR.md section 3. The enclosing page
// (DocumentViewLayout) owns the useDocumentSummary() composable and passes its state here.
withDefaults(defineProps<{
  tokens: SummaryToken[]
  timeSpent: number
  error?: string | null
  loading?: boolean
}>(), { error: null, loading: false })

const emit = defineEmits<{
  summarize: []
  cancel: []
  cite: [chunkId: string]
}>()
</script>

<style scoped>
.citation-link {
  color: var(--q-primary);
  text-decoration: underline;
}
</style>
