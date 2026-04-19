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
            <q-tab name="document" label="Document" />
          </q-tabs>
        </div>

        <q-tab-panels v-model="drawerTab" class="drawer-panels">
          <q-tab-panel name="tags" class="q-pa-md">
            <div class="tags-toolbar">
              <q-btn
                flat
                dense
                no-caps
                icon="add"
                label="Add tag"
                class="add-tag-btn"
                @click="handleCreateTag"
              />
              <div class="tags-toolbar-spacer" />
              <q-btn flat dense round size="xs" icon="visibility" @click="tagNav.showAllTags()">
                <q-tooltip>Show all</q-tooltip>
              </q-btn>
              <q-btn flat dense round size="xs" icon="visibility_off" @click="tagNav.hideAllTags(tags.map(t => t.id))">
                <q-tooltip>Hide all</q-tooltip>
              </q-btn>
            </div>
            <div v-if="tagsLoading" class="flex flex-center q-pa-lg">
              <q-spinner size="2em" color="grey-6" />
            </div>
            <div v-else-if="!tags.length" class="text-body2 text-grey-6">
              No tags in this collection.
            </div>
            <div v-else class="tags-list">
              <div
                v-for="tag in tags"
                :key="tag.id"
                class="tag-card"
                :class="{ 'is-hidden': !tagNav.isTagVisible(tag.id) }"
              >
                <div class="tag-card-header">
                  <q-btn
                    flat round dense
                    size="xs"
                    :icon="tagNav.isTagVisible(tag.id) ? 'visibility' : 'visibility_off'"
                    :class="tagNav.isTagVisible(tag.id) ? 'visibility-btn' : 'visibility-btn is-off'"
                    @click="tagNav.toggleTag(tag.id)"
                  />
                  <q-icon
                    :name="tag.pictogram || 'label'"
                    :style="{ color: tag.color || '#64748b' }"
                    size="20px"
                  />
                  <span class="tag-name">{{ tag.name }}</span>
                  <q-badge
                    v-if="tag.shorthand"
                    :label="tag.shorthand"
                    outline
                    :style="{ color: tag.color || '#64748b', borderColor: tag.color || '#64748b' }"
                    class="q-ml-auto"
                  />
                  <q-btn
                    flat
                    round
                    dense
                    size="sm"
                    icon="edit"
                    class="edit-tag-btn"
                    @click="handleEditTag(tag)"
                  >
                    <q-tooltip>Edit tag</q-tooltip>
                  </q-btn>
                </div>
                <!-- Span navigation -->
                <div v-if="tagNav.spanCount(tag.id) > 0" class="tag-nav-row">
                  <q-btn flat dense round icon="chevron_left" size="xs" @click="tagNav.navigate(tag.id, 'prev')" />
                  <span class="tag-nav-counter">
                    {{ tagNav.navIndex(tag.id) != null ? (tagNav.navIndex(tag.id)! + 1) : '–' }}/{{ tagNav.spanCount(tag.id) }}
                  </span>
                  <q-btn flat dense round icon="chevron_right" size="xs" @click="tagNav.navigate(tag.id, 'next')" />
                </div>
                <div v-if="tag.definition" class="tag-definition text-caption text-grey-7">
                  {{ tag.definition }}
                  <q-tooltip>{{ tag.definition }}</q-tooltip>
                </div>
                <TagExamples
                  :tag-name="tag.name"
                  :examples="tag.examples || []"
                  @update="(examples) => handleExamplesUpdate(tag, examples)"
                />
              </div>
            </div>
          </q-tab-panel>

          <q-tab-panel v-if="documentData" name="document" class="q-pa-md">
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
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import useDocuments from 'src/composables/useDocuments'
import type { Document } from 'src/models/documents'
import { useRoute } from 'vue-router'
import useCollections from 'src/composables/useCollections'
import useTags from 'src/composables/useTags'
import useTagsDialog from 'src/composables/dialogs/useTagsDialog'
import type { PostTag, PatchTag, Tag } from 'src/models/tags'
import TagExamples from 'src/components/TagExamples.vue'
import { useTagNavigation } from 'src/composables/useTagNavigation'

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
const { activeDocument, loadDocument } = useDocuments()
const { activeCollection, loadCollection } = useCollections()
const { tags, loading: tagsLoading, loadTagsByCollection, createTag, updateTag } = useTags()
const { openTagsDialog } = useTagsDialog()
const tagNav = useTagNavigation()

const handleCreateTag = () => {
  openTagsDialog({ dialogType: 'CREATE' }).onOk(async (tagData: PostTag) => {
    await createTag(props.collectionId, tagData)
    await loadTagsByCollection(props.collectionId)
  })
}

const handleEditTag = (tag: Tag) => {
  openTagsDialog({ dialogType: 'EDIT', tag }).onOk(async (updatedData: PatchTag) => {
    await updateTag(tag.id, updatedData)
    await loadTagsByCollection(props.collectionId)
  })
}

const handleExamplesUpdate = async (tag: Tag, examples: string[]) => {
  await updateTag(tag.id, { examples })
  await loadTagsByCollection(props.collectionId)
}

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
    await loadDocument(documentId)
  },
  { immediate: true }
)

watch(
  () => props.collectionId,
  async (collectionId) => {
    await loadCollection(collectionId)
    await loadTagsByCollection(collectionId)
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

.drawer-panels {
  flex: 1;
  overflow-y: auto;
  background: transparent;
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

.tags-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tag-card {
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.03);
  border: 1px solid rgba(15, 23, 42, 0.06);
  min-height: 80px;
}

.tag-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tag-name {
  font-size: 0.95rem;
  font-weight: 500;
  color: rgba(15, 23, 42, 0.9);
}

.tag-definition {
  margin-top: 4px;
  padding-left: 28px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tags-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 8px;
}

.tags-toolbar-spacer {
  flex: 1;
}

.add-tag-btn {
  color: #475569;
  font-size: 0.85rem;
}

.visibility-btn {
  color: #94a3b8;
  transition: color 0.15s;
}

.visibility-btn:hover {
  color: #475569;
}

.visibility-btn.is-off {
  color: #cbd5e1;
}

.tag-card.is-hidden {
  opacity: 0.45;
}

.edit-tag-btn {
  color: #94a3b8;
  opacity: 0;
  transition: opacity 0.15s;
}

.tag-card:hover .edit-tag-btn {
  opacity: 1;
}

.tag-nav-row {
  display: flex;
  align-items: center;
  gap: 2px;
  padding-left: 28px;
  margin-top: 2px;
}

.tag-nav-counter {
  font-size: 0.75rem;
  font-weight: 600;
  color: #64748b;
  min-width: 36px;
  text-align: center;
}
</style>
