<template>
  <q-page class="collection-annotations q-px-md q-pb-lg" data-testid="collection-annotations">
    <ConcordanceToolbar
      :filters="store.filters"
      :tags="tags"
      :documents="store.documents"
      :documents-error="store.documentsError"
      class="q-mb-sm"
      @change="store.setFilters"
      @reset="store.resetFilters"
    />

    <SelectionBar
      class="q-mb-xs"
      :selected-count="selection.size"
      :total="store.total"
      :hidden-selected="store.hiddenSelected"
      :shown-error="store.shownError"
      :all-selected="allMatchesSelected"
      :resolving="store.resolving"
      :tags="tags"
      :running="review.running"
      :progress="review.progress"
      :running-target="review.target"
      :report="review.report"
      :undoable="review.undoable"
      :undo-note="review.undoNote"
      @select-all="selectAllMatches"
      @clear="clearSelection"
      @deselect-hidden="store.deselectHidden"
      @reload-shown="store.loadShown"
      @review="(action, tagId) => reviewSelection(action, tagId)"
      @retry="retryReview"
      @show-changed="showChanged"
      @dismiss="review.dismiss"
      @undo="undoLast"
    />

    <div class="collection-annotations__summary" aria-live="polite">
      <span data-testid="concordance-range">{{ rangeLabel }}</span>
      <q-spinner v-if="store.loading" color="primary" size="1.2em" aria-label="Loading annotations" />
      <q-space />
      <PagerButtons v-if="store.total > PAGE_SIZE" />
    </div>

    <div v-if="store.error" class="collection-annotations__state text-negative" role="alert" data-testid="concordance-error">
      {{ store.error }}
      <q-btn flat dense no-caps color="primary" label="Retry" @click="store.load" />
    </div>
    <div
      v-else-if="!store.loading && store.page && !store.rows.length"
      class="collection-annotations__state text-grey-8"
      data-testid="concordance-empty"
    >
      {{ emptyText }}
    </div>
    <div v-else-if="!store.page" class="collection-annotations__state text-grey-7">Loading annotations…</div>

    <ConcordanceTable
      v-if="store.rows.length && !store.error"
      ref="table"
      :rows="store.rows"
      :tags="tags"
      :selected="selection.ids"
      :focused-id="selection.focused?.id ?? null"
      :loading="store.loading"
      :class="{ 'collection-annotations__stale': store.loading }"
      @open="openContext"
      @toggle="toggleRow"
      @select-page="selectPage"
    />

    <div v-if="store.total > PAGE_SIZE && store.rows.length" class="collection-annotations__summary q-mt-sm">
      <q-space />
      <PagerButtons />
    </div>

    <!-- Registered once a row is opened. -->
    <RightSidebarPanel v-if="selection.focused" :id="CONTEXT_PANEL_ID" label="Document" icon="menu_book" :order="1">
      <ChunkContextPanel
        ref="panel"
        :target-chunk-id="chunkContext.target?.chunkId ?? null"
        :document="chunkContext.document"
        :chunks="chunkContext.chunks"
        :has-before="chunkContext.hasBefore"
        :has-after="chunkContext.hasAfter"
        :focus-request="chunkContext.focusRequest"
        :loading="chunkContext.loading"
        :extending="chunkContext.extending"
        :error="chunkContext.error"
        :highlight="highlight"
        target-name="Annotated passage"
        return-label="Focus on annotation"
        @extend="chunkContext.extend"
        @reload="chunkContext.load"
        @return="returnToRow"
      >
        <template #header>
          <div class="annotation-context" data-testid="annotation-context">
            <div class="annotation-context__meta text-caption">
              <span class="annotation-context__dot" :style="{ backgroundColor: focusedTag?.color ?? '#9e9e9e' }" aria-hidden="true" />
              <span>{{ focusedTag?.name ?? 'Unknown tag' }}</span>
              <span>·</span>
              <span>{{ statusText }}</span>
            </div>
            <div
              v-if="selection.focusedGone"
              class="annotation-context__gone text-body2 text-grey-8"
              role="status"
              data-testid="annotation-context-gone"
            >
              This annotation is no longer on this page: it was deleted, or an edit took it out of
              these filters or moved it to another page.
            </div>
            <blockquote v-else class="annotation-context__text text-body2" data-testid="annotation-context-text">
              {{ selection.focused.text ?? 'The annotated text is not available yet.' }}
            </blockquote>
            <ProvenanceSummary
              v-if="!selection.focusedGone && selection.focused.provenance"
              :provenance="selection.focused.provenance"
              :type="selection.focused.type"
              :people="store.people"
              :me="userStore.getUserId"
            />
            <div
              v-if="focusedConflict && !selection.focusedGone"
              class="annotation-context__conflict text-body2"
              role="alert"
              data-testid="annotation-conflict"
            >
              <div>{{ conflictText }}</div>
              <div class="annotation-context__conflict-actions">
                <q-btn
                  dense
                  unelevated
                  no-caps
                  color="primary"
                  label="Apply to current version"
                  :disable="review.running || store.loading || savingBoundary"
                  data-testid="conflict-apply"
                  @click="applyToCurrent"
                />
                <q-btn dense flat no-caps color="primary" label="Keep" data-testid="conflict-keep" @click="keepCurrent" />
              </div>
            </div>
            <BoundaryEditor
              v-if="editingBoundary && boundary"
              ref="boundaryEditor"
              v-model:unit="boundaryUnit"
              :text="boundaryText"
              :changed="boundaryChanged"
              :saving="savingBoundary"
              :note="boundaryNote"
              @step="stepEdited"
              @use-selection="useSelectedText"
              @save="saveBoundary"
              @cancel="cancelBoundary"
            />
            <div
              v-else-if="!selection.focusedGone"
              class="annotation-context__review"
              role="group"
              aria-label="Review this annotation"
              data-testid="annotation-review"
            >
              <q-btn
                dense
                outline
                no-caps
                color="positive"
                icon="check"
                label="Approve"
                :disable="review.running || selection.focused.type === SpanType.pos"
                data-testid="row-approve"
                @click="reviewFocused(ReviewAction.approve)"
              />
              <q-btn
                dense
                outline
                no-caps
                color="warning"
                text-color="orange-10"
                icon="block"
                label="Reject"
                :disable="review.running || selection.focused.type === SpanType.neg"
                data-testid="row-reject"
                @click="reviewFocused(ReviewAction.reject)"
              />
              <q-btn
                dense
                flat
                no-caps
                color="primary"
                icon="skip_next"
                label="Skip"
                :disable="!nextRow"
                data-testid="row-skip"
                @click="skip"
              >
                <q-tooltip>Leave it as it is and show the next row</q-tooltip>
              </q-btn>
              <ReviewTagMenu
                :tags="tags"
                label="Change tag"
                :current-tag-id="selection.focused.tagId ?? null"
                :disable="review.running"
                testid="row-retag"
                @pick="tagId => reviewFocused(ReviewAction.retag, tagId)"
              />
              <q-btn
                ref="editBoundaryButton"
                dense
                flat
                no-caps
                color="primary"
                icon="straighten"
                label="Edit boundaries"
                :disable="review.running || !canEditBoundary"
                data-testid="row-edit-boundaries"
                @click="editBoundary"
              >
                <q-tooltip>{{ canEditBoundary ? 'Change where this annotation starts or ends' : 'Wait until its passage is loaded' }}</q-tooltip>
              </q-btn>
              <q-btn
                dense
                flat
                no-caps
                color="negative"
                icon="delete"
                label="Delete…"
                :disable="review.running"
                data-testid="row-delete"
                @click="reviewFocused(ReviewAction.delete)"
              />
            </div>
            <q-btn
              v-if="selection.focused.documentId"
              dense
              flat
              no-caps
              color="primary"
              icon="open_in_new"
              label="Open in document"
              class="annotation-context__open"
              :to="documentRoute"
            />
          </div>
        </template>
      </ChunkContextPanel>
    </RightSidebarPanel>
  </q-page>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, nextTick, reactive, ref, watch } from 'vue'
import { QBtn, QPage, QSpace, QSpinner, QTooltip, useQuasar } from 'quasar'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { ReviewAction, SpanType, type AnnotationListRow } from 'src/generated/api'
import { apiErrorMessage, captureSession, errorStatus } from 'src/shared/api'
import { spanWriteWarning } from 'src/shared/writeOutcome'
import { warningNotification } from 'src/shared/notification'
import { useTagSpansRepository } from 'src/features/annotations/useTagSpansRepository'
import RightSidebarPanel from 'src/app/sidebar/RightSidebarPanel.vue'
import { useRightSidebarStore } from 'src/app/sidebar/rightSidebarStore'
import ChunkContextPanel from 'src/features/documents/ChunkContextPanel.vue'
import { useChunkContext } from 'src/features/documents/useChunkContext'
import { useTagsStore } from 'src/features/annotations/tagsStore'
import { MAX_SELECTION, useAnnotationSelectionStore } from 'src/features/annotations/annotationSelectionStore'
import ConcordanceTable from './ConcordanceTable.vue'
import ConcordanceToolbar from './ConcordanceToolbar.vue'
import SelectionBar from './SelectionBar.vue'
import ReviewTagMenu from './ReviewTagMenu.vue'
import ProvenanceSummary from './ProvenanceSummary.vue'
import BoundaryEditor from './BoundaryEditor.vue'
import {
  rangeBetween, rangeText, sameRange, stepBoundary, type BoundaryHandle, type BoundaryRange, type BoundaryUnit
} from './boundaryEdit'
import { useAnnotationReviewStore, type ReviewReport } from './annotationReviewStore'
import { PAGE_SIZE, defaultFilters, useConcordanceStore } from './concordanceStore'
import { formatWhen, personName } from './provenance'
import { useUserStore } from 'src/features/auth/userStore'
import type { SelectionEntry } from 'src/features/annotations/annotationSelectionStore'

const CONTEXT_PANEL_ID = 'annotation-context'

const route = useRoute()
const $q = useQuasar()
const store = reactive(useConcordanceStore())
const selection = reactive(useAnnotationSelectionStore())
const review = reactive(useAnnotationReviewStore())
const userStore = useUserStore()
const tagsStore = useTagsStore()
const { tags } = storeToRefs(tagsStore)
const rightSidebar = useRightSidebarStore()
const chunkContext = reactive(useChunkContext())
const table = ref<InstanceType<typeof ConcordanceTable> | null>(null)
const panel = ref<InstanceType<typeof ChunkContextPanel> | null>(null)
const spansRepo = useTagSpansRepository()

const collectionId = computed(() => typeof route.params.collectionId === 'string' ? route.params.collectionId : '')

const rangeLabel = computed(() => {
  if (!store.page) return ''
  if (!store.total) return 'No matching annotations'
  const first = store.offset + 1
  const last = store.offset + store.rows.length
  return `Rows ${first}–${last} of ${store.total} matching annotations`
})

const emptyText = computed(() =>
  JSON.stringify(store.filters) === JSON.stringify(defaultFilters())
    ? 'This collection has no confirmed or proposed annotations yet.'
    : 'No annotations match these filters.')

// Previous/next page; rendered above and below the rows.
const PagerButtons = defineComponent(() => () => h('div', { class: 'row no-wrap q-gutter-x-xs' }, [
  h(QBtn, {
    dense: true,
    outline: true,
    noCaps: true,
    color: 'primary',
    icon: 'chevron_left',
    label: 'Previous',
    disable: store.offset === 0 || store.loading,
    onClick: () => store.goTo(store.offset - PAGE_SIZE)
  }),
  h(QBtn, {
    dense: true,
    outline: true,
    noCaps: true,
    color: 'primary',
    iconRight: 'chevron_right',
    label: 'Next',
    disable: store.offset + PAGE_SIZE >= store.total || store.loading,
    onClick: () => store.goTo(store.offset + PAGE_SIZE)
  })
]))

// ── Source context (shared right sidebar) ──
const highlight = computed(() => {
  if (editingBoundary.value && boundary.value) return { ...boundary.value.range, pending: true }
  const row = selection.focusedGone ? null : selection.focused
  return row?.chunkId && row.start != null && row.end != null
    ? { chunkId: row.chunkId, start: row.start, end: row.end }
    : null
})

const focusedTag = computed(() => tags.value.find(t => t.id === selection.focused?.tagId) ?? null)
const statusText = computed(() => ({
  [SpanType.pos]: 'Confirmed',
  [SpanType.auto]: 'Proposal',
  [SpanType.neg]: 'Rejected'
} as Record<string, string>)[selection.focused?.type ?? ''] ?? 'Unknown status')

const documentRoute = computed(() => {
  const row = selection.focused
  const order = chunkContext.chunks.find(c => c.id === row?.chunkId)?.order
  return {
    name: 'documentDetailV1',
    params: { collectionId: collectionId.value, documentId: row?.documentId ?? '' },
    query: {
      from: 'annotations',
      annotation: row?.id,
      chunk: row?.chunkId ?? undefined,
      order: order != null ? String(order) : undefined
    }
  }
})

function showContext (row: AnnotationListRow) {
  if (!row.documentId || !row.chunkId) return null
  return chunkContext.open({ documentId: row.documentId, chunkId: row.chunkId })
}

/** Opens the row in the sidebar; viewing context never changes the selection. */
async function openContext (row: AnnotationListRow) {
  if (row.id !== selection.focused?.id) {
    focusedConflict.value = null
    boundary.value = null
  }
  selection.focus(row)
  const opening = showContext(row)
  await nextTick() // the panel registers when the first row is opened
  rightSidebar.activate(CONTEXT_PANEL_ID)
  await opening
}

function returnToRow () {
  const row = selection.focused
  if (!row) return
  if (selection.focusedGone) {
    $q.notify({ type: 'info', message: 'This annotation is no longer on this page.' })
    return
  }
  // On narrow screens the sidebar covers the list.
  if ($q.screen.lt.md) rightSidebar.open = false
  if (store.rows.some(r => r.id === row.id)) table.value?.reveal(row.id)
  else $q.notify({ type: 'info', message: 'This annotation is not on the current page.' })
}

// ── Selection (#459) ──
const allMatchesSelected = computed(() =>
  store.hiddenSelected !== null && selection.size - store.hiddenSelected >= store.total)

function tooMany () {
  $q.notify({ type: 'warning', message: `The selection can hold at most ${MAX_SELECTION} annotations.` })
}

function toggleRow (id: string, value: boolean) {
  const version = store.rows.find(r => r.id === id)?.editVersion ?? 0
  if (!selection.toggle(id, version, value)) tooMany()
}

function selectPage (value: boolean) {
  if (!store.setPageSelected(value)) tooMany()
}

function clearSelection () {
  selection.clearSelection()
  void store.loadShown()
}

async function selectAllMatches () {
  const problem = await store.selectAllMatches()
  if (problem) $q.notify({ type: 'warning', message: problem })
}

// ── Review (#459) ──
const VERB: Record<ReviewAction, string> = {
  [ReviewAction.approve]: 'Approve',
  [ReviewAction.reject]: 'Reject',
  [ReviewAction.retag]: 'Change the tag of',
  [ReviewAction.delete]: 'Delete'
}

const nextRow = computed(() => {
  const index = store.rows.findIndex(r => r.id === selection.focused?.id)
  return index >= 0 ? store.rows[index + 1] ?? null : null
})

function plural (n: number) {
  return `${n} annotation${n === 1 ? '' : 's'}`
}

/** Asks before deleting, and before a change to annotations not on this page. */
function confirmed (action: ReviewAction, ids: string[], tagId?: string): Promise<boolean> {
  const offPage = ids.filter(id => !store.rows.some(r => r.id === id)).length
  if (action !== ReviewAction.delete && !offPage) return Promise.resolve(true)
  const tag = tagId ? tags.value.find(t => t.id === tagId)?.name : null
  const lines = [`${VERB[action]} ${plural(ids.length)}${tag ? ` to "${tag}"` : ''}?`]
  if (offPage) lines.push(`${offPage} of them ${offPage === 1 ? 'is' : 'are'} not on this page.`)
  if (action === ReviewAction.delete) {
    lines.push('Deleted annotations cannot be restored. To keep a proposal as negative feedback, reject it instead.')
  }
  return new Promise(resolve => {
    $q.dialog({
      title: action === ReviewAction.delete ? 'Delete annotations' : 'Review annotations',
      message: lines.join(' '),
      cancel: true,
      persistent: true,
      ok: { label: `${VERB[action].split(' ')[0]} ${ids.length}`, color: action === ReviewAction.delete ? 'negative' : 'primary', flat: false }
    }).onOk(() => resolve(true)).onCancel(() => resolve(false)).onDismiss(() => resolve(false))
  })
}

/** Shows the review's effect: rows read again (also the changed ones, at their current state),
 * deleted and missing ones leave the selection. Resolves when the page has been read again. */
function afterReview (report: ReviewReport) {
  const gone = report.action === ReviewAction.delete ? [...report.saved, ...report.missing] : report.missing
  if (gone.length) selection.remove(gone)
  const loading = store.load()
  void store.loadShown()
  if (report.action !== ReviewAction.approve) void store.loadDocuments()
  return loading
}

async function runReview (action: ReviewAction, items: SelectionEntry[], tagId?: string) {
  const id = collectionId.value
  if (!id || !items.length || !await confirmed(action, items.map(([i]) => i), tagId)) return null
  const report = await review.review(id, action, items, tagId ?? null)
  return report ? { report, loaded: afterReview(report) } : null
}

async function reviewSelection (action: ReviewAction, tagId?: string) {
  await runReview(action, [...selection.ids].map(i => [i, selection.versionOf(i)] as const), tagId)
}

/** Selects the annotations someone else changed meanwhile, at their current versions, to
 * look at them and review them again (#460). */
function showChanged () {
  const conflicts = review.report?.conflicts ?? []
  if (!conflicts.length) return
  selection.replace(conflicts.map(c => [c.id, c.version] as const))
  review.dismiss()
  void store.loadShown()
}

async function retryReview () {
  const id = collectionId.value
  if (!id) return
  const report = await review.retry(id)
  if (report) void afterReview(report)
}

/** A review or boundary edit of the open annotation refused because someone else changed it
 * meanwhile (#460). */
const focusedConflict = ref<{ id: string, action: ReviewAction | 'boundary', tagId?: string } | null>(null)

const conflictText = computed(() => {
  const row = selection.focused
  const conflict = focusedConflict.value
  if (!row || !conflict || row.id !== conflict.id) return ''
  const p = row.provenance
  const who = personName(p?.lastEditedBy, store.people, userStore.getUserId)
  const when = formatWhen(p?.lastEditedAt)
  const by = who === 'you' ? 'Changed in another window' : `Changed by ${who}`
  const now = `now ${statusText.value.toLowerCase()}, tag "${focusedTag.value?.name ?? 'unknown'}"`
  const away = store.rows.some(r => r.id === row.id) ? '' : ' It is no longer on this page.'
  const yours = conflict.action === 'boundary' ? 'boundary change' : VERB[conflict.action].toLowerCase()
  return `${by}${when ? ` at ${when}` : ''}: ${now}. Your ${yours} was not saved.${away}`
})

/** Reviews the open annotation; approving or rejecting it moves on to the next row. */
async function reviewFocused (action: ReviewAction, tagId?: string) {
  const row = selection.focused
  if (!row) return
  focusedConflict.value = null
  const next = nextRow.value
  const reviewed = await runReview(action, [[row.id, row.editVersion ?? 0]], tagId)
  if (!reviewed) return
  const { report } = reviewed
  if (report.conflicts.length) {
    // The page is read again (afterReview): the sidebar shows the current annotation and
    // says what happened; the selection's result line has nothing to add.
    focusedConflict.value = { id: row.id, action, tagId }
    review.dismiss()
    await reviewed.loaded
    // A change that took it out of the filters must not hide the conflict: read it as it is now.
    if (selection.focusedGone && focusedConflict.value?.id === row.id && await store.readFocused()) {
      const current = selection.focused
      if (current && current.chunkId !== chunkContext.target?.chunkId) void showContext(current)
    }
    return
  }
  const ok = report.saved.length === 1
  if (!ok) {
    $q.notify({ type: 'warning', message: report.missing.length ? 'This annotation no longer exists.' : 'The change was not saved; see the result above the list.' })
    return
  }
  if (next && (action === ReviewAction.approve || action === ReviewAction.reject)) void openContext(next)
}

/** Repeats the refused review or boundary edit against the version the sidebar shows now. */
async function applyToCurrent () {
  const conflict = focusedConflict.value
  if (!conflict || selection.focused?.id !== conflict.id) return
  if (conflict.action === 'boundary') await saveBoundary()
  else await reviewFocused(conflict.action, conflict.tagId)
}

/** Keeps the annotation as someone else changed it, dropping the refused change. */
function keepCurrent () {
  if (focusedConflict.value?.action === 'boundary') cancelBoundary()
  focusedConflict.value = null
}

// ── Boundary editing (#461) ──
/** The range being edited for the annotation `id`; `range` is not saved yet. */
const boundary = ref<{ id: string, range: BoundaryRange } | null>(null)
const boundaryUnit = ref<BoundaryUnit>('word')
const boundaryNote = ref<string | null>(null)
const savingBoundary = ref(false)
const boundaryEditor = ref<InstanceType<typeof BoundaryEditor> | null>(null)
const editBoundaryButton = ref<InstanceType<typeof QBtn> | null>(null)

/** The range of the open annotation as saved. */
const focusedRange = computed<BoundaryRange | null>(() => {
  const row = selection.focusedGone ? null : selection.focused
  return row?.chunkId && row.start != null && row.end != null
    ? { chunkId: row.chunkId, start: row.start, end: row.end }
    : null
})
const editingBoundary = computed(() => !!boundary.value && boundary.value.id === selection.focused?.id &&
  !selection.focusedGone)
// Its anchor chunk must be loaded, to edit it in the passage shown.
const canEditBoundary = computed(() => {
  const range = focusedRange.value
  return !!range && chunkContext.chunks.some(c => c.id === range.chunkId)
})
const boundaryText = computed(() => boundary.value ? rangeText(chunkContext.chunks, boundary.value.range) : '')
const boundaryChanged = computed(() => !!boundary.value && !!focusedRange.value &&
  !sameRange(boundary.value.range, focusedRange.value))

async function editBoundary () {
  const row = selection.focused
  const range = focusedRange.value
  if (!row || !range || !canEditBoundary.value) return
  boundary.value = { id: row.id, range }
  boundaryNote.value = null
  await nextTick()
  boundaryEditor.value?.$el?.querySelector?.('button')?.focus()
}

async function cancelBoundary () {
  boundary.value = null
  boundaryNote.value = null
  await nextTick()
  editBoundaryButton.value?.$el?.focus?.()
}

function stepEdited (handle: BoundaryHandle, direction: -1 | 1) {
  const b = boundary.value
  if (!b) return
  const next = stepBoundary(chunkContext.chunks, b.range, handle, direction, boundaryUnit.value)
  if (!next) {
    boundaryNote.value = `The ${handle} cannot move further: the start stays before the end, within the text ` +
      'shown (show earlier or later text to go further).'
    return
  }
  b.range = next
  boundaryNote.value = null
}

function useSelectedText () {
  const b = boundary.value
  if (!b) return
  const selected = panel.value?.textSelection() ?? null
  const range = selected ? rangeBetween(chunkContext.chunks, selected[0], selected[1]) : null
  if (!range) {
    boundaryNote.value = selected
      ? 'The selection must be within one continuous part of the document.'
      : 'Select the new text in the passage first.'
    return
  }
  b.range = range
  boundaryNote.value = null
}

/** The page read again after a change of the open annotation; it stays open, also when the
 * change took it out of the filters, and its passage follows it to another chunk. */
async function followFocused () {
  const loading = store.load()
  void store.loadShown()
  await loading
  if (selection.focusedGone) await store.readFocused()
  const current = selection.focusedGone ? null : selection.focused
  if (current?.chunkId && !chunkContext.chunks.some(c => c.id === current.chunkId)) void showContext(current)
}

/**
 * Saves the edited range of the open annotation at the version shown (#460): a start in
 * another chunk moves the annotation there (#436). The edit becomes the change to undo,
 * from the range the annotation had at that version. A conflict keeps the editor open
 * with the current annotation shown, to save against it or keep it.
 */
async function saveBoundary () {
  const row = selection.focused
  const b = boundary.value
  const saved = focusedRange.value
  const id = collectionId.value
  if (!row || !b || !saved || b.id !== row.id || !id || savingBoundary.value || sameRange(b.range, saved)) return
  const inScope = selection.captureScope()
  const inSession = captureSession()
  const applies = () => inScope() && inSession() && selection.focused?.id === row.id
  savingBoundary.value = true
  focusedConflict.value = null
  try {
    const result = await spansRepo.update(row.id, id, {
      start: b.range.start,
      end: b.range.end,
      ...(b.range.chunkId !== saved.chunkId ? { chunkId: b.range.chunkId } : {})
    }, row.editVersion ?? 0)
    const warning = spanWriteWarning(result, 'saved')
    if (warning) warningNotification(warning)
    if (!inScope() || !inSession()) return
    const version = result.editVersion ?? 0
    selection.noteVersions({ [row.id]: version })
    review.noteChange({
      kind: 'boundary',
      items: [{
        id: row.id,
        version,
        values: { start: saved.start, end: saved.end, ...(result.chunkId !== saved.chunkId ? { chunkId: saved.chunkId } : {}) }
      }]
    })
    if (boundary.value === b) boundary.value = null
    await followFocused()
    if (applies() && !boundary.value) await cancelBoundary()
  } catch (e) {
    if (!applies()) return
    const status = errorStatus(e)
    if (status === 409) {
      focusedConflict.value = { id: row.id, action: 'boundary' }
      await followFocused()
    } else if (status === 404) {
      boundary.value = null
      $q.notify({ type: 'warning', message: 'This annotation no longer exists.' })
      await followFocused()
    } else {
      $q.notify({ type: 'negative', message: await apiErrorMessage(e, 'The boundaries could not be saved.') })
    }
  } finally {
    savingBoundary.value = false
  }
}

// ── Undo (#461) ──
async function undoLast () {
  const id = collectionId.value
  if (!id) return
  focusedConflict.value = null
  const report = await review.undo(id)
  if (!report) return
  await afterReview(report)
  const current = selection.focusedGone ? null : selection.focused
  if (current?.chunkId && !chunkContext.chunks.some(c => c.id === current.chunkId)) void showContext(current)
}

function skip () {
  if (nextRow.value) void openContext(nextRow.value)
}

// ── Workspace state across navigation ──
onBeforeRouteLeave(() => {
  store.scrollY = window.scrollY
})

watch(collectionId, async (id) => {
  if (!id) return
  chunkContext.clear()
  const returning = store.collectionId === id && !!store.page
  void tagsStore.fetchTagsByCollection(id)
  const loading = store.open(id)
  if (returning) {
    // Back from a document: the same place, then the rows as they are now.
    await nextTick()
    window.scrollTo(0, store.scrollY)
    if (selection.focused) void showContext(selection.focused)
  }
  await loading
  // A boundary edit may have moved the annotation to another chunk.
  const row = selection.focused
  if (returning && row && !selection.focusedGone && row.chunkId && row.chunkId !== chunkContext.target?.chunkId) {
    void showContext(row)
  }
}, { immediate: true })
</script>

<style scoped>
.collection-annotations__summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 12px;
  min-height: 36px;
  font-size: 0.85rem;
  color: rgba(0, 0, 0, 0.72);
}

.collection-annotations__state {
  padding: 24px 0;
}

.collection-annotations__stale {
  opacity: 0.55;
  transition: opacity 0.2s;
}

.annotation-context {
  margin-top: 6px;
}

.annotation-context__meta {
  display: flex;
  align-items: center;
  gap: 6px;
  color: rgba(0, 0, 0, 0.7);
}

.annotation-context__dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

.annotation-context__text {
  margin: 4px 0;
  padding: 4px 8px;
  border-left: 3px solid #ffd54f;
  background: #fffbe6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 9em;
  overflow-y: auto;
}

.annotation-context__gone {
  margin: 4px 0;
  padding: 4px 8px;
  border-left: 3px solid #bdbdbd;
}

.annotation-context__review {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 6px;
  margin: 6px 0;
}

.annotation-context__open {
  margin-left: -6px;
}

.annotation-context__conflict {
  margin: 6px 0;
  padding: 4px 8px;
  border-left: 3px solid var(--q-warning);
  background: rgba(242, 192, 55, 0.12);
}

.annotation-context__conflict-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 6px;
  margin-top: 4px;
}
</style>
