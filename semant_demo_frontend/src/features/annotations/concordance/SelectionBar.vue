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
      <span v-if="running" class="selection-bar__progress" role="status" aria-live="polite">
        <q-spinner size="1.1em" color="primary" />
        Saving {{ progress }} / {{ runningTarget }}…
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
        v-if="report.failed.length"
        dense
        flat
        no-caps
        color="primary"
        icon="refresh"
        :label="`Retry ${report.failed.length}`"
        :disable="running"
        data-testid="review-retry"
        @click="emit('retry')"
      />
      <q-btn dense flat round size="sm" icon="close" aria-label="Dismiss the review result" @click="emit('dismiss')" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { QBtn, QIcon, QSpinner } from 'quasar'
import { ReviewAction, type Tag } from 'src/generated/api'
import ReviewTagMenu from './ReviewTagMenu.vue'
import type { ReviewReport } from './annotationReviewStore'

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
}>()

const emit = defineEmits<{
  'select-all': []
  clear: []
  'deselect-hidden': []
  'reload-shown': []
  review: [action: ReviewAction, tagId?: string]
  retry: []
  dismiss: []
}>()

const canSelectAll = computed(() => props.total > 0 && !props.allSelected)

const PAST: Record<ReviewAction, string> = {
  [ReviewAction.approve]: 'Approved',
  [ReviewAction.reject]: 'Rejected',
  [ReviewAction.retag]: 'Retagged',
  [ReviewAction.delete]: 'Deleted'
}

const hasProblems = computed(() => {
  const r = props.report
  return !!r && (r.failed.length > 0 || r.missing.length > 0 || r.searchNotUpdated > 0 || !!r.error)
})

const reportText = computed(() => {
  const r = props.report
  if (!r) return ''
  const uncertain = r.failed.filter(f => f.uncertain).length
  const parts = [`${PAST[r.action]} ${r.saved.length} of ${r.target}.`]
  if (r.failed.length - uncertain) parts.push(`${r.failed.length - uncertain} failed.`)
  if (uncertain) parts.push(`${uncertain} uncertain (the server did not confirm; they may have been saved).`)
  if (r.missing.length) parts.push(`${r.missing.length} no longer exist and were removed from the selection.`)
  if (r.searchNotUpdated) parts.push('Tag-filtered search was not updated for some of them; repeating the action updates it.')
  if (r.error) parts.push(r.error)
  if (r.saved.length && r.action !== ReviewAction.delete && r.failed.length) parts.push('Saved changes are kept.')
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

.selection-bar__report {
  padding: 4px 8px;
  border-left: 3px solid var(--q-positive);
  background: rgba(33, 186, 69, 0.06);
}

.selection-bar__report--problem {
  border-left-color: var(--q-warning);
  background: rgba(242, 192, 55, 0.12);
}
</style>
