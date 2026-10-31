<template>
  <div class="selection-bar" role="region" aria-label="Selection and review" data-testid="selection-bar">
    <div class="selection-bar__line">
      <span v-if="selectedCount" class="selection-bar__count" data-testid="concordance-selected">
        {{ selectedCount }} selected
      </span>
      <span v-else class="selection-bar__none">No annotations selected</span>
      <q-btn
        v-if="canSelectAll"
        flat
        dense
        no-caps
        color="primary"
        :label="`Select all ${total} matches`"
        :loading="resolving"
        data-testid="select-all-matches"
        @click="emit('select-all')"
      />
      <q-btn
        v-if="selectedCount"
        flat
        dense
        no-caps
        color="primary"
        label="Clear selection"
        data-testid="clear-selection"
        @click="emit('clear')"
      />
    </div>

    <div v-if="hiddenSelected" class="selection-bar__hidden" role="status" data-testid="hidden-selected">
      <q-icon name="visibility_off" size="1.1em" aria-hidden="true" />
      <span>{{ hiddenSelected }} selected not shown by these filters (or no longer existing).</span>
      <q-btn flat dense no-caps color="primary" label="Deselect them" data-testid="deselect-hidden" @click="emit('deselect-hidden')" />
    </div>
    <div v-else-if="shownError" class="selection-bar__hidden text-negative" role="status">
      {{ shownError }}
      <q-btn flat dense no-caps color="primary" label="Retry" @click="emit('reload-shown')" />
    </div>

    <div v-if="selectedCount" class="selection-bar__actions" role="group" aria-label="Review the selected annotations">
      <q-btn
        dense
        outline
        no-caps
        color="positive"
        icon="check"
        :label="`Approve ${selectedCount}`"
        :disable="running"
        data-testid="review-approve"
        @click="emit('review', ReviewAction.approve)"
      />
      <q-btn
        dense
        outline
        no-caps
        color="warning"
        text-color="orange-10"
        icon="block"
        :label="`Reject ${selectedCount}`"
        :disable="running"
        data-testid="review-reject"
        @click="emit('review', ReviewAction.reject)"
      />
      <ReviewTagMenu
        :tags="tags"
        :label="`Change tag of ${selectedCount}`"
        :disable="running"
        testid="review-retag"
        @pick="tagId => emit('review', ReviewAction.retag, tagId)"
      />
      <q-btn
        dense
        outline
        no-caps
        color="negative"
        icon="delete"
        :label="`Delete ${selectedCount}…`"
        :disable="running"
        data-testid="review-delete"
        @click="emit('review', ReviewAction.delete)"
      />
      <q-btn
        dense
        outline
        no-caps
        color="primary"
        icon="label"
        :label="`Assign attribute to ${selectedCount}…`"
        :disable="running || assignBusy"
        data-testid="assign-attribute"
        @click="emit('assign')"
      />
      <span v-if="running" class="selection-bar__progress" role="status" aria-live="polite">
        <q-spinner size="1.1em" color="primary" />
        {{ runningTarget ? `Saving ${progress} / ${runningTarget}…` : 'Updating search…' }}
      </span>
    </div>

    <div
      v-if="report"
      class="selection-bar__report"
      :class="{ 'selection-bar__report--problem': hasProblems }"
      role="status"
      aria-live="polite"
      data-testid="review-report"
    >
      <span>{{ reportText }}</span>
      <q-btn
        v-if="report.failed.length || report.unsynced.length"
        dense
        flat
        no-caps
        color="primary"
        icon="refresh"
        :label="report.failed.length ? `Retry ${report.failed.length}` : 'Update search'"
        :disable="running"
        data-testid="review-retry"
        @click="emit('retry')"
      />
      <q-btn
        v-if="report.conflicts.length"
        dense
        flat
        no-caps
        color="primary"
        icon="manage_search"
        label="Show changed"
        :disable="running"
        data-testid="review-show-changed"
        @click="emit('show-changed')"
      >
        <q-tooltip>Select only the changed annotations, as they are now, to review them again</q-tooltip>
      </q-btn>
      <q-btn dense flat round size="sm" icon="close" aria-label="Dismiss the review result" @click="emit('dismiss')" />
    </div>

    <div
      v-if="assignReport"
      class="selection-bar__report selection-bar__report--assign"
      :class="{ 'selection-bar__report--problem': assignReportHasProblems(assignReport) }"
      role="status"
      aria-live="polite"
      data-testid="assign-report"
    >
      <div class="selection-bar__report-head">
        <span class="selection-bar__report-title" data-testid="assign-report-title">{{ assignSummary!.title }}</span>
        <q-space />
        <q-btn
          v-if="assignReport.failed.length"
          dense
          flat
          no-caps
          color="primary"
          icon="refresh"
          :label="`Retry ${assignReport.failed.length}`"
          :disable="assignBusy"
          data-testid="assign-retry"
          @click="emit('assign-retry')"
        />
        <q-btn
          v-if="assignReport.conflicts.length"
          dense
          flat
          no-caps
          color="primary"
          icon="manage_search"
          label="Show changed"
          :disable="assignBusy"
          data-testid="assign-show-changed"
          @click="emit('assign-show-changed')"
        >
          <q-tooltip>Select only the changed annotations, as they are now, to assign them again</q-tooltip>
        </q-btn>
        <q-btn dense flat round size="sm" icon="close" aria-label="Dismiss the assignment result" @click="emit('assign-dismiss')" />
      </div>
      <ul v-if="assignSummary!.lines.length" class="selection-bar__report-list" data-testid="assign-report-lines">
        <li v-for="(line, i) in assignSummary!.lines" :key="i">
          <span v-if="line.count !== null" class="selection-bar__report-count">{{ line.count }}</span>
          <span class="selection-bar__report-label">{{ line.label }}</span>
          <span v-if="line.detail" class="selection-bar__report-detail">{{ line.detail }}</span>
        </li>
      </ul>
    </div>

    <div v-if="undoable || undoNote" class="selection-bar__undo" role="status" data-testid="undo-bar">
      <span>{{ undoText }}</span>
      <q-btn
        v-if="undoable"
        dense
        flat
        no-caps
        color="primary"
        icon="undo"
        label="Undo"
        :disable="running"
        data-testid="undo"
        @click="emit('undo')"
      >
        <q-tooltip>Restore what these annotations were before, unless someone changed them since</q-tooltip>
      </q-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { QBtn, QIcon, QSpace, QSpinner, QTooltip } from 'quasar'
import { ReviewAction, type Attribute, type Tag } from 'src/generated/api'
import { assignReportHasProblems, assignReportSummary } from 'src/features/attributes/assignment'
import type { AssignReport } from 'src/features/attributes/attributeAssignStore'
import ReviewTagMenu from './ReviewTagMenu.vue'
import type { ChangeKind, ReportAction, ReviewReport, UndoableChange } from './annotationReviewStore'

const props = defineProps<{
  selectedCount: number
  /** Matches of the current filters. */
  total: number
  /** Selected annotations the filters do not show; null while unknown. */
  hiddenSelected: number | null
  shownError: string | null
  /** All matches are already selected or cannot be (none). */
  allSelected: boolean
  resolving: boolean
  tags: Tag[]
  running: boolean
  progress: number
  runningTarget: number
  report: ReviewReport | null
  /** The last change, while it can be undone (#461). */
  undoable?: UndoableChange | null
  /** Why the last change cannot be undone. */
  undoNote?: string | null
  /** An attribute assignment of the selection is under way, or one of its members' (#331). */
  assignBusy?: boolean
  assignReport?: AssignReport | null
  /** The attribute of `assignReport`. */
  assignAttribute?: Attribute | null
}>()

const emit = defineEmits<{
  'select-all': []
  clear: []
  'deselect-hidden': []
  'reload-shown': []
  review: [action: ReviewAction, tagId?: string]
  retry: []
  'show-changed': []
  dismiss: []
  undo: []
  assign: []
  'assign-retry': []
  'assign-show-changed': []
  'assign-dismiss': []
}>()

const assignSummary = computed(() =>
  props.assignReport ? assignReportSummary(props.assignReport, props.assignAttribute ?? null) : null)

const canSelectAll = computed(() => props.total > 0 && !props.allSelected)

const PAST: Record<ReportAction, string> = {
  [ReviewAction.approve]: 'Approved',
  [ReviewAction.reject]: 'Rejected',
  [ReviewAction.retag]: 'Retagged',
  [ReviewAction.delete]: 'Deleted',
  restore: 'Undo: restored'
}

const CHANGE: Record<ChangeKind, string> = {
  [ReviewAction.approve]: 'approved',
  [ReviewAction.reject]: 'rejected',
  [ReviewAction.retag]: 'changed the tag of',
  boundary: 'changed the boundaries of'
}

const undoText = computed(() => {
  const change = props.undoable
  if (!change) return props.undoNote ?? ''
  const n = change.items.length
  return `Last change: you ${CHANGE[change.kind]} ${n} annotation${n === 1 ? '' : 's'}.`
})

const hasProblems = computed(() => {
  const r = props.report
  return !!r && (r.failed.length > 0 || r.conflicts.length > 0 || r.missing.length > 0 || r.unsynced.length > 0 ||
    !!r.error)
})

const reportText = computed(() => {
  const r = props.report
  if (!r) return ''
  const uncertain = r.failed.filter(f => f.uncertain).length
  const parts = [`${PAST[r.action]} ${r.saved.length} of ${r.target}.`]
  if (r.failed.length - uncertain) parts.push(`${r.failed.length - uncertain} failed.`)
  if (uncertain) parts.push(`${uncertain} uncertain (the server did not confirm; they may have been saved).`)
  if (r.conflicts.length) {
    const n = r.conflicts.length
    parts.push(r.action === 'restore'
      ? `${n} ${n === 1 ? 'was' : 'were'} changed again since then; not restored.`
      : `${n} ${n === 1 ? 'was' : 'were'} changed by someone else since you selected ${n === 1 ? 'it' : 'them'}; not saved.`)
  }
  if (r.missing.length) {
    parts.push(r.action === 'restore'
      ? `${r.missing.length} no longer exist.`
      : `${r.missing.length} no longer exist and were removed from the selection.`)
  }
  if (r.unsynced.length) parts.push(`Search by tag does not reflect some changes yet (${r.unsynced.length} ${r.unsynced.length === 1 ? 'passage' : 'passages'}).`)
  if (r.error) parts.push(r.error)
  if (r.saved.length && r.action !== ReviewAction.delete && (r.failed.length || r.conflicts.length)) {
    parts.push('Saved changes are kept.')
  }
  return parts.join(' ')
})
</script>

<style scoped>
.selection-bar {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.85rem;
}

.selection-bar__line,
.selection-bar__actions,
.selection-bar__hidden,
.selection-bar__report {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
}

.selection-bar__count {
  font-weight: 600;
  color: var(--q-primary);
}

.selection-bar__none {
  color: rgba(0, 0, 0, 0.6);
}

.selection-bar__hidden {
  color: rgba(0, 0, 0, 0.75);
}

.selection-bar__progress {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.selection-bar__undo {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
  color: rgba(0, 0, 0, 0.75);
}

.selection-bar__report {
  padding: 4px 8px;
  border-left: 3px solid var(--q-positive);
  background: rgba(33, 186, 69, 0.06);
}

.selection-bar__report--assign {
  flex-direction: column;
  align-items: stretch;
  gap: 2px;
}

.selection-bar__report-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
}

.selection-bar__report-title {
  font-weight: 600;
}

.selection-bar__report-list {
  margin: 0;
  padding: 0 0 2px;
  list-style: none;
}

.selection-bar__report-list li {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 2px 6px;
}

.selection-bar__report-count {
  min-width: 1.6em;
  padding: 0 5px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.08);
  font-weight: 600;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.selection-bar__report-label {
  font-weight: 500;
}

.selection-bar__report-detail {
  color: rgba(0, 0, 0, 0.72);
}

.selection-bar__report--problem {
  border-left-color: var(--q-warning);
  background: rgba(242, 192, 55, 0.12);
}
</style>
