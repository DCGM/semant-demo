<template>
  <div class="column q-gutter-y-md">
    <q-btn
      color="secondary"
      icon="auto_awesome"
      label="Summarize Results"
      :loading="loading"
      :disable="disable"
      @click="emit('summarize')"
    />

    <div class="row no-wrap q-gutter-sm">
      <q-select
        :model-value="brevity"
        @update:model-value="emit('update:brevity', $event)"
        :options="SUMMARY_BREVITY_OPTIONS"
        label="Brevity"
        dense
        outlined
        class="col"
        emit-value
        map-options
      />
      <q-select
        :model-value="scope"
        @update:model-value="emit('update:scope', $event)"
        :options="SUMMARY_SCOPE_OPTIONS"
        label="Scope"
        dense
        outlined
        class="col"
        emit-value
        map-options
      />
    </div>

    <q-card v-if="tokens.length" flat bordered class="bg-blue-grey-1">
      <q-card-section>
        <div class="text-caption text-grey q-mb-sm">Time spent: {{ timeSpent.toFixed(2) }}s</div>
        <div class="text-body2" style="white-space: pre-wrap;">
          <template v-for="(token, idx) in tokens" :key="idx">
            <span v-if="token.type === 'text'">{{ token.value }}</span>
            <a
              v-else
              href="#"
              class="citation-link"
              @click.prevent="emit('cite', token.docNumber)"
            >[{{ token.docNumber }}]</a>
          </template>
        </div>
      </q-card-section>
    </q-card>
    <div v-else class="text-caption text-grey-7">
      Summarize the search results to get an overview with citations of the individual results.
    </div>
  </div>
</template>

<script setup lang="ts">
import { SUMMARY_BREVITY_OPTIONS, SUMMARY_SCOPE_OPTIONS } from 'src/composables/useSearchSummary'
import type { SummaryToken } from 'src/composables/useSearchSummary'

withDefaults(defineProps<{
  tokens: SummaryToken[]
  timeSpent: number
  brevity: string
  scope: string
  loading?: boolean
  disable?: boolean
}>(), { loading: false, disable: false })

const emit = defineEmits<{
  summarize: []
  cite: [docNumber: number]
  'update:brevity': [value: string]
  'update:scope': [value: string]
}>()
</script>

<style scoped>
.citation-link {
  color: var(--q-primary);
  text-decoration: underline;
}
</style>
