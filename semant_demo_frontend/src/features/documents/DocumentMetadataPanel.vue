<template>
  <div>
    <div v-for="field in fields" :key="field.label" class="meta-row">
      <div class="meta-label">{{ field.label }}</div>
      <div class="meta-value">{{ field.value }}</div>
    </div>
    <div class="meta-row">
      <div class="meta-label">Original</div>
      <div class="meta-value">
        <OriginalSourceLink v-if="hasOriginal" :document="document" />
        <span v-else class="text-grey-7">Not available</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Document } from 'src/generated/api'
import OriginalSourceLink from './OriginalSourceLink.vue'
import { originalSourceUrl } from './originalSource'

// Bibliographic fields of a document; a missing value shows as "-". The original is the
// digitized document in its digital library, when a trustworthy link exists (#255).
const props = defineProps<{ document: Document }>()

const hasOriginal = computed(() => originalSourceUrl(props.document) !== null)

const fields = computed(() => {
  const d = props.document
  return [
    { label: 'Authors', value: d.author?.join(', ') || '-' },
    { label: 'Year issued', value: d.yearIssued ?? '-' },
    { label: 'Language', value: d.language || '-' },
    { label: 'Publisher', value: d.publisher || '-' },
    { label: 'Place of publication', value: d.placeOfPublication || '-' },
    { label: 'Document type', value: d.documentType || '-' },
    { label: 'Keywords', value: d.keywords?.join(', ') || '-' }
  ]
})
</script>

<style scoped>
.meta-row {
  padding: 12px 0;
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
}

.meta-row:last-child {
  border-bottom: 0;
}

.meta-label {
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgba(71, 85, 105, 0.85);
  margin-bottom: 4px;
}

.meta-value {
  font-size: 0.98rem;
  color: rgba(15, 23, 42, 0.95);
  word-break: break-word;
}
</style>
