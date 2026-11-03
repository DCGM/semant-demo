<template>
  <q-page class="scan-preview column no-wrap">
    <div class="scan-preview__header row items-center q-px-md q-py-sm">
      <div class="col" style="min-width: 0">
        <div class="text-subtitle1 ellipsis" data-testid="scan-preview-title">{{ title || documentId }}</div>
        <div class="text-caption text-grey-7 ellipsis" :title="lastEvent">
          <span v-if="lastEvent" data-testid="scan-preview-event" aria-live="polite">{{ lastEvent }}</span>
          <span v-else>Scan viewer preview (#543), on its own until the document workspace (#545) uses it.</span>
        </div>
      </div>
    </div>
    <div class="col scan-preview__pane">
      <DocumentImagePane
        ref="pane"
        :document-id="documentId"
        :page-id="pageId"
        :document-title="title"
        @update:page-id="onPageId"
        @line-select="lastEvent = describe('Selected', $event)"
        @line-focus="lastEvent = describe('Focused', $event)"
      />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDocumentsRepository } from 'src/features/documents/useDocumentsRepository'
import DocumentImagePane, { type ScanTarget } from './DocumentImagePane.vue'

// The scan viewer on its own (src/router/previewRoutes.ts): the page is kept in `?page=`,
// the last line event is shown so it can be checked by hand and by browser tests, and the
// pane is reachable for focus requests (`window.__scanPreview`, tests only).

const props = defineProps<{ documentId: string }>()

const route = useRoute()
const router = useRouter()
const pane = ref<InstanceType<typeof DocumentImagePane> | null>(null)
const title = ref('')
const lastEvent = ref('')

const pageId = computed(() => typeof route.query.page === 'string' ? route.query.page : null)

const describe = (what: string, t: ScanTarget) =>
  `${what} line ${t.lineId} on page ${t.pageId}${t.offset === undefined ? '' : ` at offset ${t.offset}`}`

function onPageId (id: string) {
  if (id !== pageId.value) void router.replace({ query: { ...route.query, page: id } })
}

watch(() => props.documentId, async (id) => {
  title.value = ''
  try {
    const doc = await useDocumentsRepository().getById(id)
    if (id === props.documentId) title.value = doc.title ?? ''
  } catch {
    // The title is decoration here; the pane reports its own errors.
  }
}, { immediate: true })

// Browser tests send focus requests the way the text pane will (#544).
;(window as unknown as { __scanPreview?: unknown }).__scanPreview = {
  focus: (request: Parameters<NonNullable<typeof pane.value>['focus']>[0]) => pane.value?.focus(request)
}
</script>

<style scoped>
.scan-preview {
  height: calc(100vh - 50px);
}

/* A fixed height: a new event line must not resize (and refit) the viewer. */
.scan-preview__header {
  flex: 0 0 auto;
  height: 56px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.12);
  gap: 8px;
  flex-wrap: nowrap;
  overflow: hidden;
}

.scan-preview__pane {
  min-height: 0;
}
</style>
