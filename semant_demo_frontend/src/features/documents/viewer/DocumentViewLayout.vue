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
        <!-- A fixed parent route, not browser history, so direct links go back predictably (#253). -->
        <q-btn
          flat round dense
          icon="arrow_back"
          :to="backToDocumentsRoute"
          aria-label="Back to collection documents"
        >
          <q-tooltip>Back to collection documents</q-tooltip>
        </q-btn>

        <div class="q-ml-sm" v-if="documentData">
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

        <q-separator vertical inset class="q-mx-sm" />

        <q-btn
          flat round
          size="md"
          icon="menu"
          :color="drawerOpen ? undefined : 'primary'"
          :aria-label="drawerOpen ? 'Hide panel' : 'Show panel'"
          :aria-expanded="drawerOpen"
          @click="drawerOpen = !drawerOpen"
        >
          <q-tooltip>{{ drawerOpen ? 'Hide panel' : 'Show panel' }}</q-tooltip>
        </q-btn>
      </q-toolbar>
    </q-header>
    <q-drawer
      v-model="drawerOpen"
      side="right"
      :width="360"
      :breakpoint="0"
      bordered
      class="doc-info-drawer"
    >
      <div class="drawer-content">
        <div class="tabs-wrapper q-mx-md q-mt-md">
          <q-tabs v-model="drawerTab" dense align="justify" class="drawer-tabs" indicator-color="transparent">
            <q-tab name="tags" label="Tags" />
            <q-tab name="ai">
              <div class="ai-tab-label">
                <span>AI assist</span>
                <q-spinner
                  v-if="aiAssist.isRunning.value || aiAssist.isSelectionRunning.value"
                  color="primary"
                  size="1em"
                  class="q-ml-xs"
                />
              </div>
            </q-tab>
            <q-tab name="document" label="Document" />
          </q-tabs>
        </div>

        <q-tab-panels v-model="drawerTab" animated>
          <q-tab-panel name="tags" class="q-pa-md">
            <DocumentTagsPanel ref="tagsPanelRef" :collection-id="collectionId" :document-id="documentId" />
          </q-tab-panel>

          <q-tab-panel name="ai" class="q-pa-md ai-panel">
            <AiAssistPanel :collection-id="collectionId" :document-id="documentId" />
          </q-tab-panel>

          <q-tab-panel v-if="documentData" name="document" class="q-pa-md">
            <DocumentMetadataPanel :document="documentData" />
          </q-tab-panel>
        </q-tab-panels>
      </div>
    </q-drawer>

    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Document } from 'src/generated/api'
import { useDocumentsStore } from 'src/features/documents/documentsStore'
import DocumentMetadataPanel from 'src/features/documents/DocumentMetadataPanel.vue'
import { useUserCollectionsStore } from 'src/features/user_collections/userCollectionsStore'
import AiAssistPanel from 'src/features/annotations/AiAssistPanel.vue'
import DocumentTagsPanel from 'src/features/annotations/DocumentTagsPanel.vue'
import { useTagsStore } from 'src/features/annotations/tagsStore'
import useAiAssistance from 'src/features/annotations/useAiAssistance'
import useTagSpans from 'src/features/annotations/useTagSpans'

// The document view: header, the side drawer with the tags, AI assist and document
// tools, and the reader (child route). It loads the document, collection and tags and
// clears the annotation and AI state when the document or collection changes.
interface Props {
  collectionId: string
  documentId: string
}

const props = defineProps<Props>()
const route = useRoute()
const drawerOpen = ref(true)
const drawerTab = ref('tags')
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
const tagsPanelRef = ref<InstanceType<typeof DocumentTagsPanel> | null>(null)

function onCtrlF(e: KeyboardEvent) {
  if (!e.ctrlKey) return
  if (e.key.toLowerCase() !== 'f') return
  if (drawerTab.value !== 'tags') return
  e.preventDefault()
  drawerOpen.value = true
  void nextTick(() => tagsPanelRef.value?.focusSearch())
}

// Track which drawer tab is active so the document page can hide auto spans
// outside of the AI assist tab.
watch(drawerTab, (val) => {
  aiAssist.aiTabActive.value = val === 'ai'
  if (val !== 'ai') aiAssist.highlightedAutoSpanId.value = null
}, { immediate: true })

// External callers (e.g. the in-text selection popover's "Suggest tags"
// button) can request that we switch to the AI assist tab via
// ``aiAssist.requestOpenAiPanel()``. The composable bumps a nonce we watch
// here so each call re-triggers, even if we're already on the tab.
watch(
  () => aiAssist.aiPanelRequestNonce.value,
  (n, prev) => {
    if (n === prev) return
    drawerOpen.value = true
    drawerTab.value = 'ai'
  }
)

onBeforeUnmount(() => {
  // Leaving the document view aborts document-wide and selection runs; their late
  // events are ignored. Suggestions already saved stay saved.
  aiAssist.reset()
  aiAssist.aiTabActive.value = false
  aiAssist.highlightedAutoSpanId.value = null
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
    // Reset shared AI assistance state so stale "Processed N chunks" / pending
    // suggestions from the previous document don't leak into the new one.
    aiAssist.reset()
    tagSpans.clearAll()
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

.doc-info-drawer {
  background: #f8fafc;
  color: #1f2937;
}

.drawer-content {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.tabs-wrapper {
  flex-shrink: 0;
  background: rgba(15, 23, 42, 0.06);
  border-radius: 10px;
  padding: 4px;
}

.drawer-tabs {
  border-radius: 8px;
}

.drawer-tabs :deep(.q-tab) {
  border-radius: 7px;
  min-height: 32px;
}

.drawer-tabs :deep(.q-tab--active) {
  background: #ffffff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.1);
}

/* Make the q-tab-panels container fill the drawer's available height so the
   AI tab can use a flex layout and never overflow. The other tabs (Tags,
   Document) keep their natural height and scroll vertically when their
   content exceeds the drawer. */
.drawer-content :deep(.q-tab-panels) {
  flex: 1 1 0;
  min-height: 0;
  background: transparent;
  overflow: hidden;
}
.drawer-content :deep(.q-panel) {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
.drawer-content :deep(.q-tab-panel) {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
}
/* The AI panel manages its own internal scrolling (only the suggestions
   list scrolls), so the panel itself must never scroll as a whole. */
.drawer-content :deep(.q-tab-panel.ai-panel) {
  overflow: hidden;
}
</style>
