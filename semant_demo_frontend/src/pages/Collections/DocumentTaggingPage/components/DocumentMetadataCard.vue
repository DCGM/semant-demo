<template>
  <q-card flat class="right-panel-menu">
    <q-card-section class="right-panel-menu-section">
      <div class="metadata-header">
        <div>
          <div class="text-subtitle1 text-weight-bold">Document info</div>
          <!-- <div v-if="document" class="text-caption text-grey-7">
            {{ document.id }}
          </div> -->
        </div>

        <q-btn flat round dense icon="close" @click="emit('close')">
          <q-tooltip>Close document info</q-tooltip>
        </q-btn>
      </div>

      <q-separator class="q-mb-md q-mt-sm" />

      <div v-if="document" class="metadata-grid">
        <div
          v-for="item in metadataItems"
          :key="item.label"
          class="metadata-item"
        >
          <div class="text-caption text-grey-7">{{ item.label }}</div>
          <div class="text-body2 text-weight-medium">{{ item.value }}</div>
        </div>

        <div v-if="description" class="metadata-description">
          <div class="text-caption text-grey-7 q-mb-xs">Description</div>
          <div class="text-body2">{{ description }}</div>
        </div>
      </div>

      <div v-else class="text-body2 text-grey-7">
        Document metadata is not available yet.
      </div>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { SemantDemoSchemasDocument } from 'src/generated/api/models/SemantDemoSchemasDocument'

const props = defineProps<{
  document: SemantDemoSchemasDocument | null
}>()

const emit = defineEmits<{
  close: []
}>()

const formatValue = (value: unknown) => {
  if (value === null || value === undefined || value === '') {
    return '—'
  }

  if (value instanceof Date) {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium'
    }).format(value)
  }

  return String(value)
}

const metadataItems = computed(() => {
  const document = props.document
  if (!document) return []

  return [
    { label: 'Title', value: formatValue(document.title) },
    { label: 'Subtitle', value: formatValue(document.subtitle) },
    { label: 'Author', value: formatValue(document.author) },
    { label: 'Publisher', value: formatValue(document.publisher) },
    { label: 'Library', value: formatValue(document.library) },
    { label: 'Language', value: formatValue(document.language) },
    { label: 'Year issued', value: formatValue(document.yearIssued) },
    { label: 'Date issued', value: formatValue(document.dateIssued) },
    { label: 'Document type', value: formatValue(document.documentType) },
    { label: 'Genre', value: formatValue(document.genre) },
    { label: 'Place term', value: formatValue(document.placeTerm) },
    { label: 'Public', value: formatValue(document._public ? 'Yes' : 'No') }
  ].filter((item) => item.value !== '—')
})

const description = computed(() => props.document?.description ?? '')
</script>

<style scoped>
.metadata-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.metadata-grid {
  display: grid;
  grid-template-columns: repeat(1, minmax(0, 1fr));
  gap: 12px;
}

.metadata-item {
  padding: 0;
  border-radius: 10px;
  background: white;
  min-width: 0;
}

.metadata-description {
  grid-column: 1 / -1;
  padding: 10px 12px;
  border-radius: 10px;
  background: white;
}
</style>
