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
        <div class="q-ml-sm">
          <BackLink :to="backRoute" :label="backText" :aria-label="backLabel" />
          <template v-if="documentData">
            <div class="text-caption text-grey-6">Document</div>
            <div class="text-h5 text-weight-medium">{{ documentData.title || 'Untitled document' }}</div>
            <div v-if="documentData.subtitle" class="text-body2 text-grey-7 q-mt-xs">
              {{ documentData.subtitle }}
            </div>
            <OriginalSourceLink :document="documentData" class="text-body2 q-mt-xs" />
          </template>
        </div>

        <q-space />

        <div class="collection-context text-right q-pr-sm">
          <div class="text-caption text-grey-6">Collection</div>
          <div class="text-body1 text-weight-medium">{{ activeCollectionName }}</div>
        </div>
      </q-toolbar>
    </q-header>

    <!-- The tools are panels of the app's right sidebar; they get the document's context through props. -->
    <RightSidebarPanel :id="DOCUMENT_SIDEBAR_PANELS.tags" label="Tags" icon="sell" :order="0">
      <DocumentTagsPanel ref="tagsPanelRef" :collection-id="collectionId" :document-id="documentId" />
    </RightSidebarPanel>
    <!-- fill: only the suggestion list scrolls, the run controls stay in view -->
    <RightSidebarPanel
      :id="DOCUMENT_SIDEBAR_PANELS.ai"
      label="AI Tagging"
      icon="auto_awesome"
      :order="1"
      :busy="aiAssist.isRunning.value || aiAssist.isSelectionRunning.value"
      fill
    >
      <AiAssistPanel :collection-id="collectionId" :document-id="documentId" />
    </RightSidebarPanel>
    <!-- fill: the rendered summary scrolls on its own; the Summarize/Cancel controls stay in view -->
    <RightSidebarPanel
      :id="DOCUMENT_SIDEBAR_PANELS.summary"
      label="Summary"
      icon="summarize"
      :order="1.5"
      :busy="documentSummary.summarizing.value"
      fill
    >
      <DocumentSummaryPanel
        :tokens="documentSummary.tokens.value"
        :time-spent="documentSummary.timeSpent.value"
        :length="documentSummary.length.value"
        :truncated="documentSummary.truncated.value"
        :summarized-chunks="documentSummary.summarizedChunks.value"
        :total-chunks="documentSummary.totalChunks.value"
        :error="documentSummary.error.value"
        :loading="documentSummary.summarizing.value"
        @summarize="onSummarizeDocument"
        @cancel="documentSummary.cancel"
        @update:length="documentSummary.setLength"
        @cite="documentSummary.cite"
      />
    </RightSidebarPanel>
    <RightSidebarPanel :id="DOCUMENT_SIDEBAR_PANELS.metadata" label="Document" icon="description" :order="2">
      <DocumentMetadataPanel v-if="documentData" :document="documentData" />
    </RightSidebarPanel>

    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import RightSidebarPanel from 'src/app/sidebar/RightSidebarPanel.vue'
import { useRightSidebarStore } from 'src/app/sidebar/rightSidebarStore'
import { Document } from 'src/generated/api'
import { useDocumentsStore } from 'src/features/documents/documentsStore'
import DocumentMetadataPanel from 'src/features/documents/DocumentMetadataPanel.vue'
import OriginalSourceLink from 'src/features/documents/OriginalSourceLink.vue'
import { useUserCollectionsStore } from 'src/features/user_collections/userCollectionsStore'
import AiAssistPanel from 'src/features/annotations/AiAssistPanel.vue'
import DocumentTagsPanel from 'src/features/annotations/DocumentTagsPanel.vue'
import { useTagsStore } from 'src/features/annotations/tagsStore'
import useAiAssistance from 'src/features/annotations/useAiAssistance'
import useTagSpans from 'src/features/annotations/useTagSpans'
import DocumentSummaryPanel from 'src/features/documents/DocumentSummaryPanel.vue'
import useDocumentSummary from 'src/features/documents/useDocumentSummary'
import { DOCUMENT_SIDEBAR_PANELS } from './documentSidebar'
import BackLink from 'src/shared/ui/BackLink.vue'

// The document view: header, the tags, AI tagging and document tools as panels of the
// app's right sidebar, and the reader (child route). It loads the document, collection and tags and
// clears the annotation and AI state when the document or collection changes.
interface Props {
  collectionId: string
  documentId: string
}

const props = defineProps<Props>()
const route = useRoute()
const sidebar = useRightSidebarStore()
const layoutRef = ref<unknown>(null)
const layoutHeight = ref<string>('auto')
const documentsStore = useDocumentsStore()
const { activeDocument } = storeToRefs(documentsStore)
const { fetchDocument } = documentsStore
const collectionsStore = useUserCollectionsStore()
const { activeCollection } = storeToRefs(collectionsStore)
const { fetchCollection } = collectionsStore
const { fetchTagsByCollection } = useTagsStore()
const aiAssist = useAiAssistance()
const tagSpans = useTagSpans()
const documentSummary = useDocumentSummary()
const tagsPanelRef = ref<InstanceType<typeof DocumentTagsPanel> | null>(null)

function onSummarizeDocument() {
  void documentSummary.summarize(props.collectionId, props.documentId)
}

// Ctrl+F searches the tags while the Tags panel is the sidebar's active panel (also when
// the sidebar is closed or mini); otherwise the browser's own find is left alone.
function onCtrlF(e: KeyboardEvent) {
  if (!e.ctrlKey) return
  if (e.key.toLowerCase() !== 'f') return
  if (sidebar.activePanelId !== DOCUMENT_SIDEBAR_PANELS.tags) return
  e.preventDefault()
  sidebar.activate(DOCUMENT_SIDEBAR_PANELS.tags)
  void nextTick(() => tagsPanelRef.value?.focusSearch())
}

// The document page shows auto spans only while the AI Tagging panel is the active one.
watch(() => sidebar.activePanelId === DOCUMENT_SIDEBAR_PANELS.ai, (active) => {
  aiAssist.aiPanelActive.value = active
  if (!active) aiAssist.highlightedAutoSpanId.value = null
}, { immediate: true })

onBeforeUnmount(() => {
  // Leaving the document view aborts document-wide and selection runs; their late
  // events are ignored. Suggestions already saved stay saved.
  aiAssist.reset()
  aiAssist.aiPanelActive.value = false
  aiAssist.highlightedAutoSpanId.value = null
  // A summary in flight is dropped too; it is not persisted, unlike AI suggestions.
  documentSummary.reset()
})

const documentData = computed<Document>(() => activeDocument.value!)

const activeCollectionName = computed(() => {
  if (activeCollection.value?.id === props.collectionId) {
    return activeCollection.value.name
  }
  return 'Unknown collection'
})

const layoutStyle = computed(() => ({
  '--document-layout-height': layoutHeight.value
}))

// Opened from the collection's annotation workspace (#329), it leads back there. (No route
// when the layout is mounted without a router, as in component tests.)
const fromAnnotations = computed(() => route?.query.from === 'annotations')
const backLabel = computed(() => fromAnnotations.value ? 'Back to annotations' : 'Back to collection documents')
const backText = computed(() => fromAnnotations.value ? 'Annotations' : 'Documents')
const backRoute = computed(() => ({
  name: fromAnnotations.value ? 'collectionAnnotations' : 'collectionDocumentsTagging',
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
    // Reset shared AI assistance state so stale "Processed N chunks" / pending
    // suggestions from the previous document don't leak into the new one.
    aiAssist.reset()
    tagSpans.clearAll()
    documentSummary.reset() // a stale/in-flight summary of the previous document is dropped
    await fetchDocument(documentId)
  },
  { immediate: true }
)

watch(
  () => props.collectionId,
  async (collectionId) => {
    // A run of the previous collection must not add suggestions to the new one, and its
    // annotations (the same chunk can be in both) must not stay on screen.
    aiAssist.reset()
    tagSpans.clearAll()
    documentSummary.reset() // a stale/in-flight summary of the previous collection is dropped
    await fetchCollection(collectionId)
    await fetchTagsByCollection(collectionId)
  },
  { immediate: true }
)

onMounted(async () => {
  await nextTick()
  updateLayoutHeight()

  window.addEventListener('resize', updateLayoutHeight, { passive: true })
  window.addEventListener('scroll', updateLayoutHeight, { passive: true })
  window.addEventListener('keydown', onCtrlF)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateLayoutHeight)
  window.removeEventListener('scroll', updateLayoutHeight)
  window.removeEventListener('keydown', onCtrlF)
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
</style>
