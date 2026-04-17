<template>
  <q-layout
    ref="layoutRef"
    view="hHh LpR lff"
    container
    class="document-detail-layout"
    :style="layoutStyle"
  >
    <q-header class="doc-header q-pl-sm" bordered>
      <q-toolbar class="doc-header-toolbar">
        <q-btn flat round dense icon="arrow_back" :to="backToDocumentsRoute">
          <q-tooltip>Back to documents</q-tooltip>
        </q-btn>

        <div class="q-ml-sm">
          <div class="text-caption text-grey-6">Document detail</div>
          <div class="text-h5 text-weight-medium">{{ documentData.title || 'Untitled document' }}</div>
          <div v-if="documentData.subtitle" class="text-body2 text-grey-7 q-mt-xs">
            {{ documentData.subtitle }}
          </div>
        </div>

        <q-space />

        <div class="collection-context text-right q-pr-sm">
          <div class="text-caption text-grey-6">Collection</div>
          <div class="text-body1 text-weight-medium">{{ activeCollectionName }}</div>
        </div>
      </q-toolbar>
    </q-header>

    <q-page-container>
      <router-view />
    </q-page-container>

    <q-drawer
      v-model="drawerOpen"
      side="right"
      :width="400"
      :breakpoint="1024"
      show-if-above
      bordered
      class="doc-info-drawer"
    >
      <div class="drawer-content q-pa-md">
        <div class="text-h6 text-weight-medium q-mb-md">Document info</div>

        <div class="meta-row">
          <div class="meta-label">Authors</div>
          <div class="meta-value">{{ documentData.author?.join(', ') || '-' }}</div>
        </div>

        <div class="meta-row">
          <div class="meta-label">Year issued</div>
          <div class="meta-value">{{ documentData.yearIssued ?? '-' }}</div>
        </div>

        <div class="meta-row">
          <div class="meta-label">Language</div>
          <div class="meta-value">{{ documentData.language || '-' }}</div>
        </div>

        <div class="meta-row">
          <div class="meta-label">Publisher</div>
          <div class="meta-value">{{ documentData.publisher || '-' }}</div>
        </div>

        <div class="meta-row">
          <div class="meta-label">Place of publication</div>
          <div class="meta-value">{{ documentData.placeOfPublication || '-' }}</div>
        </div>

        <div class="meta-row">
          <div class="meta-label">Document type</div>
          <div class="meta-value">{{ documentData.documentType || '-' }}</div>
        </div>

        <div class="meta-row">
          <div class="meta-label">Keywords</div>
          <div class="meta-value">{{ documentData.keywords?.join(', ') || '-' }}</div>
        </div>
      </div>
    </q-drawer>
  </q-layout>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import useDocuments from 'src/composables/useDocuments'
import type { Document } from 'src/models/documents'
import { useRoute } from 'vue-router'
import useCollections from 'src/composables/useCollections'

interface Props {
  collectionId: string
  documentId: string
}

const props = defineProps<Props>()
const route = useRoute()
const drawerOpen = ref(true)
const layoutRef = ref<unknown>(null)
const layoutHeight = ref<string>('auto')
const { activeDocument, loadDocument } = useDocuments()
const { activeCollection, loadCollection } = useCollections()

const fallbackDocument: Document = {
  id: props.documentId || 'doc-2026-0148',
  title: 'Untitled document',
  author: ['Unknown Author'],
  yearIssued: null,
  language: null,
  publisher: null,
  placeOfPublication: null,
  documentType: null,
  subtitle: null,
  keywords: []
}

const documentData = computed<Document>(() => activeDocument.value ?? fallbackDocument)

const activeCollectionName = computed(() => {
  if (activeCollection.value?.id === props.collectionId) {
    return activeCollection.value.name
  }
  return 'Unknown collection'
})

const layoutStyle = computed(() => ({
  '--document-layout-height': layoutHeight.value
}))

const backToDocumentsRoute = computed(() => ({
  name: 'collectionDocumentsTagging',
  params: {
    collectionId:
      props.collectionId ||
      (typeof route.params.collectionId === 'string' ? route.params.collectionId : '')
  }
}))

const getLayoutElement = (): HTMLElement | null => {
  const target = layoutRef.value as { $el?: Element } | HTMLElement | null

  if (!target) {
    return null
  }

  if (target instanceof HTMLElement) {
    return target
  }

  if (target.$el instanceof HTMLElement) {
    return target.$el
  }

  return null
}

const updateLayoutHeight = () => {
  const layoutElement = getLayoutElement()
  if (!layoutElement) {
    return
  }

  const { top } = layoutElement.getBoundingClientRect()
  const normalizedTop = Math.max(top, 0)
  const computedHeight = Math.max(window.innerHeight - normalizedTop, 320)

  layoutHeight.value = `${Math.round(computedHeight)}px`
}

watch(
  () => props.documentId,
  async (documentId) => {
    await loadDocument(documentId)
  },
  { immediate: true }
)

watch(
  () => props.collectionId,
  async (collectionId) => {
    await loadCollection(collectionId)
  },
  { immediate: true }
)

onMounted(async () => {
  await nextTick()
  updateLayoutHeight()

  window.addEventListener('resize', updateLayoutHeight, { passive: true })
  window.addEventListener('scroll', updateLayoutHeight, { passive: true })
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateLayoutHeight)
  window.removeEventListener('scroll', updateLayoutHeight)
})
</script>

<style scoped>
.document-detail-layout {
  height: var(--document-layout-height, auto);
  min-height: 0;
  background: #eef2f7;
}

.doc-header {
  background: #ffffff;
  color: #1f2a37;
  border-bottom: 1px solid rgba(15, 23, 42, 0.1);
}

.doc-header-toolbar {
  min-height: 88px;
}

.collection-context {
  max-width: 360px;
}

.doc-header :deep(.q-btn) {
  color: #334155;
}

.doc-header :deep(.text-grey-6) {
  color: #64748b !important;
}

.doc-header :deep(.text-grey-7) {
  color: #475569 !important;
}

.doc-header :deep(.text-h5) {
  color: #0f172a;
}

.doc-info-drawer {
  background: #f8fafc;
  color: #1f2937;
}

.drawer-content {
  height: 100%;
  overflow-y: auto;
}

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
