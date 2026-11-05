<template>
  <q-layout
    ref="layoutRef"
    view="hHh LpR lff"
    container
    class="document-detail-layout"
    :style="layoutStyle"
  >
    <q-header class="doc-header">
      <DocumentHeader
        :title="documentData ? (documentData.title || 'Untitled document') : '…'"
        :detail="documentData?.subtitle ?? ''"
        :document="documentData"
        :back="{ to: backRoute, label: backText, ariaLabel: backLabel }"
      >
        <div class="collection-context ellipsis" :title="`Collection: ${activeCollectionName}`" data-testid="document-collection">
          <q-icon name="collections_bookmark" size="16px" class="q-mr-xs" aria-hidden="true" />
          <span class="sr-only">Collection: </span><span>{{ activeCollectionName }}</span>
        </div>
      </DocumentHeader>
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
    <!-- fill: the conversation scrolls; the question input stays in view -->
    <RightSidebarPanel
      :id="DOCUMENT_SIDEBAR_PANELS.chat"
      label="Chat"
      icon="forum"
      :order="1.75"
      :busy="documentChat.streaming.value"
      fill
    >
      <!-- keyed: another document gets a fresh panel, so a typed question is not asked about it -->
      <ScopedChatPanel
        :key="`${collectionId}:${documentId}`"
        :messages="documentChat.messages.value"
        :streaming="documentChat.streaming.value"
        scope-label="Asking about this document's passages in the collection"
        @ask="documentChat.ask"
        @stop="documentChat.stop"
        @new-conversation="documentChat.reset"
        @cite="(source) => citeInReader(source.chunkId, source.order)"
      />
    </RightSidebarPanel>
    <RightSidebarPanel :id="DOCUMENT_SIDEBAR_PANELS.metadata" label="Document" icon="description" :order="2">
      <DocumentMetadataPanel v-if="documentData" :document="documentData" />
    </RightSidebarPanel>

    <q-page-container>
      <!-- No access to the collection (or it is gone): the corpus document is still public. -->
      <q-banner v-if="collectionUnavailable" class="bg-amber-1 text-grey-9 q-ma-md" rounded role="alert" data-testid="collection-unavailable">
        <template #avatar><q-icon name="lock" color="amber-9" /></template>
        This collection cannot be opened: it does not exist or is not shared with you. Its
        annotations are not shown.
        <template #action>
          <q-btn flat no-caps color="primary" label="Open the public document" :to="documentLink(documentId)" />
        </template>
      </q-banner>
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
import { useUserCollectionsStore } from 'src/features/user_collections/userCollectionsStore'
import AiAssistPanel from 'src/features/annotations/AiAssistPanel.vue'
import DocumentTagsPanel from 'src/features/annotations/DocumentTagsPanel.vue'
import { useTagsStore } from 'src/features/annotations/tagsStore'
import useAiAssistance from 'src/features/annotations/useAiAssistance'
import useTagSpans from 'src/features/annotations/useTagSpans'
import DocumentSummaryPanel from 'src/features/documents/DocumentSummaryPanel.vue'
import useDocumentSummary from 'src/features/documents/useDocumentSummary'
import { citeInReader } from 'src/features/documents/readerCitation'
import ScopedChatPanel from 'src/features/chat/ScopedChatPanel.vue'
import useScopedChat from 'src/features/chat/useScopedChat'
import { DOCUMENT_SIDEBAR_PANELS } from './documentSidebar'
import DocumentHeader from 'src/features/documents/workspace/DocumentHeader.vue'
import { documentLink } from 'src/features/documents/workspace/documentLink'

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
// Document chat (#248): one in-memory conversation per document; it starts empty on
// another document or collection and is dropped when the view unmounts.
const documentChat = useScopedChat(() => ({
  kind: 'document', collectionId: props.collectionId, documentId: props.documentId
}))
const tagsPanelRef = ref<InstanceType<typeof DocumentTagsPanel> | null>(null)
/** The collection could not be read (no access, or it does not exist). */
const collectionUnavailable = ref(false)

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

const documentData = computed<Document | null>(() => activeDocument.value ?? null)

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
    collectionUnavailable.value = false
    await fetchCollection(collectionId)
    if (collectionId !== props.collectionId) return
    collectionUnavailable.value = activeCollection.value?.id !== collectionId
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
  background: #fff;
}

.doc-header {
  background: #ffffff;
  color: #1f2a37;
}

.collection-context {
  flex: 0 1 auto;
  min-width: 0;
  max-width: 280px;
  font-size: 0.85rem;
  font-weight: 500;
  color: #475569;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
}
</style>
