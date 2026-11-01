import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'
import { AssignSource, type AttributeAssignResult } from 'src/generated/api'
import { apiErrorMessage, captureSession, errorStatus, useApi } from 'src/shared/api'
import { useAnnotationSelectionStore } from 'src/features/annotations/annotationSelectionStore'
import type { AssignChange } from './assignment'

/** Annotations sent per assignment request (the backend accepts at most 200). */
export const ASSIGN_BATCH = 200

/** An annotation and the `attributeVersion` an assignment to it expects. */
export type AssignTarget = readonly [id: string, attributeVersion: number]

/** An annotation whose assignment did not succeed, or may not have; a retry sends it again. */
export interface AssignFailure {
  id: string
  message: string
  /** The write timed out or its answer was lost: it may have been applied. */
  uncertain: boolean
  version: number
}

/** An annotation the rules refused (not approved, a tag the attribute does not apply to, a
 * retired value, …): not changed, and not retried. */
export interface AssignRefusal {
  id: string
  step: string
  message: string
}

/** What one assignment (and its retries) did, per annotation. */
export interface AssignReport {
  attributeId: string
  change: AssignChange
  /** Annotations it targeted when it started. */
  target: number
  saved: string[]
  failed: AssignFailure[]
  /** Changed by someone else since selected: not changed, and not retried; their versions now. */
  conflicts: AssignTarget[]
  refused: AssignRefusal[]
  /** Not annotations of the collection (any more). */
  missing: string[]
  /** Saved, but their change record could not be written. */
  unrecorded: string[]
  /** Targets not sent because a request was refused or the selection changed. */
  notSent: number
  /** Why it stopped early. */
  error: string | null
}

/** The first request was refused as a whole: nothing was saved, looked at or possibly written. */
export const refusedWhole = (r: AssignReport) =>
  !!r.error && !r.saved.length && !r.conflicts.length && !r.refused.length && !r.missing.length &&
  !r.unrecorded.length && !r.failed.some(f => f.uncertain)

/**
 * Attribute assignments of the annotation workspace (#331, ADR 0011): one attribute's values
 * added, removed or replaced on one annotation (a row or the sidebar) or on the selection, sent
 * in parts of `ASSIGN_BATCH`, each annotation with the `attributeVersion` it was seen at.
 *
 * At most one assignment per annotation is under way at a time (`pending`): its controls wait,
 * since a second one would expect the version the first is about to change. Every answer's
 * `versions` and `values` are the annotation as it is now; `onAnswer` hands them to the rows and
 * the selection keeps the versions this user saved. Writes are best effort and reported per
 * annotation; nothing is rolled back. Retrying sends only failed and uncertain items; conflicts
 * and refusals are not retried. There is no undo of assignments.
 *
 * Leaving the collection or signing out stops further parts and drops the report; a change of
 * the selection's members stops a selection's assignment, the rest reported as not sent.
 */
export const useAttributeAssignStore = defineStore('attributeAssign', () => {
  const api = useApi().default
  const selection = useAnnotationSelectionStore()
  /** A selection's assignment is under way. */
  const running = ref(false)
  const progress = ref(0)
  const target = ref(0)
  /** Annotations with an assignment under way. */
  const pending = ref<Set<string>>(new Set())
  const report = shallowRef<AssignReport | null>(null)
  let run = 0

  function hold (ids: string[], on: boolean) {
    const next = new Set(pending.value)
    for (const id of ids) {
      if (on) next.add(id)
      else next.delete(id)
    }
    pending.value = next
  }

  const isPending = (id: string) => pending.value.has(id)

  function request (collectionId: string, attributeId: string, change: AssignChange, part: AssignTarget[]) {
    return api.assignAttributeValuesApiUserCollectionsCollectionIdAnnotationsAttributesAssignPost({
      collectionId,
      attributeAssignRequest: {
        attributeId,
        annotationIds: part.map(([id]) => id),
        expectedVersions: Object.fromEntries(part),
        mode: change.mode,
        valueIds: change.valueIds,
        source: AssignSource.manual
      }
    })
  }

  /** Files one answer's items into `into`. */
  function file (into: AssignReport, result: AttributeAssignResult, expected: Record<string, number>) {
    const versions = result.versions ?? {}
    const saved = result.succeeded ?? []
    into.saved.push(...saved)
    selection.noteAttributeVersions(Object.fromEntries(saved.filter(id => id in versions).map(id => [id, versions[id]!])))
    for (const f of result.failed ?? []) {
      const id = f.itemId
      if (!id) continue
      if (f.step === 'find_annotation') into.missing.push(id)
      else if (f.step === 'record_attribute_changes') into.unrecorded.push(id)
      else if (f.step === 'edit_conflict') into.conflicts.push([id, versions[id] ?? expected[id] ?? 0])
      // A rule refused it (`check_*`): retrying changes nothing. Anything else (a failed read or
      // write) may succeed when sent again.
      else if (f.step.startsWith('check_')) into.refused.push({ id, step: f.step, message: f.message })
      else into.failed.push({ id, message: f.message, uncertain: !!f.uncertain, version: expected[id] ?? 0 })
    }
  }

  const emptyReport = (attributeId: string, change: AssignChange, count: number): AssignReport => ({
    attributeId,
    change,
    target: count,
    saved: [],
    failed: [],
    conflicts: [],
    refused: [],
    missing: [],
    unrecorded: [],
    notSent: 0,
    error: null
  })

  /**
   * Sends `items` into `into`; false when stopped because the context changed (the answers
   * are dropped then). `unchanged`: the selection still has its members; once it has not, the
   * remaining parts are not sent.
   */
  async function send (collectionId: string, into: AssignReport, items: AssignTarget[], applies: () => boolean,
    unchanged: () => boolean, onAnswer: (result: AttributeAssignResult) => void) {
    progress.value = 0
    const failures = (list: AssignTarget[], message: string, uncertain = false) =>
      list.map(([id, version]) => ({ id, message, uncertain, version }))
    for (let i = 0; i < items.length; i += ASSIGN_BATCH) {
      if (!applies()) return false
      if (!unchanged()) {
        into.notSent += items.length - i
        into.error = `Stopped because the selection changed; ${items.length - i} were not sent.`
        return true
      }
      const part = items.slice(i, i + ASSIGN_BATCH)
      const ids = part.map(([id]) => id)
      hold(ids, true)
      try {
        const result = await request(collectionId, into.attributeId, into.change, part)
        if (!applies()) return false
        onAnswer(result)
        file(into, result, Object.fromEntries(part))
      } catch (e) {
        if (!applies()) return false
        const status = errorStatus(e)
        // 503: the store cannot take assignments (`annotation_attributes add-schema` not run);
        // answered before any write, so a refusal like a 4xx, not a lost answer.
        if (status !== null && (status < 500 || status === 503)) {
          into.error = await apiErrorMessage(e, 'The assignment was refused.')
          into.failed.push(...failures(part, into.error ?? ''))
          into.notSent += items.length - i - part.length
          into.failed.push(...failures(items.slice(i + part.length), 'Not sent.'))
          return true
        }
        // A 5xx or lost answer: the part may have been applied.
        into.failed.push(...failures(part, 'No answer from the server.', true))
      } finally {
        hold(ids, false)
      }
      progress.value = Math.min(items.length, i + part.length)
    }
    return true
  }

  function startRun () {
    const mine = ++run
    const inScope = selection.captureScope()
    const inSession = captureSession()
    return { mine, applies: () => mine === run && inScope() && inSession() }
  }

  /**
   * Assigns `change` of the attribute to the selection's members `items`; returns the report,
   * or null when the collection was left or the session ended meanwhile (nothing more is sent).
   */
  async function assign (collectionId: string, attributeId: string, change: AssignChange, items: AssignTarget[],
    onAnswer: (result: AttributeAssignResult) => void): Promise<AssignReport | null> {
    const targets = [...new Map(items)]
    // One assignment per annotation at a time: a row's own one finishes first.
    if (running.value || targets.some(([id]) => isPending(id))) return null
    const { mine, applies } = startRun()
    const next = emptyReport(attributeId, change, targets.length)
    target.value = targets.length
    running.value = true
    try {
      if (!await send(collectionId, next, targets, applies, selection.captureMembership(), onAnswer)) return null
      // A request refused as a whole changed nothing: its dialog says why, the bar shows nothing.
      if (!refusedWhole(next)) report.value = next
      return next
    } finally {
      if (mine === run) running.value = false
    }
  }

  /**
   * Assigns `change` to one annotation (a row or the sidebar), unless an assignment of it is
   * under way; returns its report, or null when nothing was sent or the context changed. It
   * does not replace the selection's report.
   */
  async function assignOne (collectionId: string, attributeId: string, change: AssignChange, item: AssignTarget,
    onAnswer: (result: AttributeAssignResult) => void): Promise<AssignReport | null> {
    if (isPending(item[0])) return null
    const inScope = selection.captureScope()
    const inSession = captureSession()
    const next = emptyReport(attributeId, change, 1)
    const sent = await send(collectionId, next, [item], () => inScope() && inSession(), () => true, onAnswer)
    return sent ? next : null
  }

  /** Sends the failed and uncertain items of the last report again. */
  async function retry (collectionId: string, onAnswer: (result: AttributeAssignResult) => void): Promise<AssignReport | null> {
    const last = report.value
    if (!last || !last.failed.length) return last
    const { mine, applies } = startRun()
    const next: AssignReport = {
      ...last,
      failed: [],
      notSent: 0,
      error: null,
      saved: [...last.saved],
      conflicts: [...last.conflicts],
      refused: [...last.refused],
      missing: [...last.missing],
      unrecorded: [...last.unrecorded]
    }
    target.value = last.failed.length
    running.value = true
    try {
      const items = last.failed.map(f => [f.id, f.version] as const)
      if (!await send(collectionId, next, items, applies, selection.captureMembership(), onAnswer)) return null
      report.value = next
      return next
    } finally {
      if (mine === run) running.value = false
    }
  }

  function dismiss () {
    report.value = null
  }

  /** Forgets the report and stops a running assignment (sign-out, another collection). */
  function clear () {
    run++
    running.value = false
    progress.value = 0
    pending.value = new Set()
    report.value = null
  }

  return { running, progress, target, pending, report, isPending, assign, assignOne, retry, dismiss, clear }
})
