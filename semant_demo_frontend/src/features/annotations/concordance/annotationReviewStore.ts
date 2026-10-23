import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'
import { ReviewAction, type AnnotationReviewResult, type AnnotationValues } from 'src/generated/api'
import { apiErrorMessage, captureSession, errorStatus, useApi } from 'src/shared/api'
import { useAnnotationSelectionStore, type SelectionEntry } from '../annotationSelectionStore'

/** Annotations sent per review request (the backend accepts at most 200). */
export const REVIEW_BATCH = 200
/** (chunk, tag) pairs per search repair request (the backend accepts at most 1,000). */
export const SYNC_BATCH = 1000

/** An annotation whose review write did not succeed, or may not have. */
export interface ReviewFailure {
  id: string
  message: string
  /** The write timed out or its answer was lost: it may have been applied. */
  uncertain: boolean
  /** The version the write expected, which a retry expects again. */
  version: number
}

/** An annotation someone else changed since the version the review expected (#460). */
export interface ReviewConflict {
  id: string
  /** Its version now. */
  version: number
}

/** A review action, or `restore`: the undo of the last change (#461). */
export type ReportAction = ReviewAction | 'restore'

/** A change the workspace can undo: a review or a boundary edit. */
export type ChangeKind = Exclude<ReviewAction, 'delete'> | 'boundary'

/** One annotation of an undoable change: its version after the change and the values the
 * change replaced. */
export interface UndoItem {
  id: string
  version: number
  values: AnnotationValues
}

/** The last change made in the workspace, while it can be undone. */
export interface UndoableChange {
  kind: ChangeKind
  items: UndoItem[]
}

/** What one review action (and its retries) did, per annotation. */
export interface ReviewReport {
  action: ReportAction
  tagId: string | null
  /** Annotations the action targeted when it started. */
  target: number
  saved: string[]
  /** Failed or uncertain writes: the ones a retry sends again. */
  failed: ReviewFailure[]
  /** Changed by someone else since selected: not changed, and not retried. */
  conflicts: ReviewConflict[]
  /** Not annotations of the collection (any more): deleted meanwhile, or never there. */
  missing: string[]
  /** Saved changes that tag-filtered search does not reflect yet, as the `chunkId:tagId`
   * pairs to re-derive; a retry repairs them, also those of deleted annotations. */
  unsynced: string[]
  /** Targets not sent because a request was refused (e.g. access was revoked) or the
   * selection changed. */
  notSent: number
  /** Why the action stopped early. */
  error: string | null
  /** The values an undo (`restore`) puts back, per annotation, which its retry sends again. */
  values?: Record<string, AnnotationValues>
}

/**
 * Review actions of the annotation workspace (#459): approve, reject, retag or delete a
 * fixed list of annotations, sent in parts of `REVIEW_BATCH`. The targets are resolved when
 * the action starts (the explicit selection or one row), so later filter changes never
 * widen it. Writes are best effort and reported per annotation; nothing is rolled back.
 * Each annotation is sent with the version it was selected at (#460): one changed by someone
 * else since is refused and reported as a conflict, never retried; this user's saved writes
 * move the selection's versions on. Retrying sends only failed and uncertain items (an
 * uncertain write that landed counts as saved) and repairs the search references whose
 * update failed.
 *
 * Undo (#461): the last approve, reject, retag or boundary edit of at most `REVIEW_BATCH`
 * annotations can be undone once (`undoable`), from the previous values the backend returned
 * (the values the browser saw, for a boundary edit). The undo restores each annotation only
 * while it has the version the change left; the others are reported, as a review reports
 * them. It is kept in memory only. A deletion, or a larger change, replaces it with a note
 * saying it cannot be undone.
 *
 * Leaving the collection or signing out stops sending further parts and drops the report
 * and the undo; writes already sent are kept by the backend. A change of the selection's members stops
 * sending further parts and reports the rest as not sent. A refused part (4xx) stops the
 * action; a lost answer marks its part uncertain and continues with the next.
 */
export const useAnnotationReviewStore = defineStore('annotationReview', () => {
  const api = useApi().default
  const selection = useAnnotationSelectionStore()
  const running = ref(false)
  /** Annotations sent so far by the running action, of `target`. */
  const progress = ref(0)
  const target = ref(0)
  const report = shallowRef<ReviewReport | null>(null)
  const undoable = shallowRef<UndoableChange | null>(null)
  /** Why the last change cannot be undone. */
  const undoNote = ref<string | null>(null)
  let run = 0

  function emptyReport (action: ReportAction, tagId: string | null, target: number): ReviewReport {
    return { action, tagId, target, saved: [], failed: [], conflicts: [], missing: [], unsynced: [], notSent: 0, error: null }
  }

  /** The request of `into`'s action for one part of its annotations. */
  function request (collectionId: string, into: ReviewReport, part: SelectionEntry[]): Promise<AnnotationReviewResult> {
    if (into.action === 'restore') {
      const values = into.values ?? {}
      return api.restoreCollectionAnnotationsApiUserCollectionsCollectionIdAnnotationsRestorePost({
        collectionId,
        annotationRestoreRequest: {
          items: part.map(([id, version]) => ({ id, expectedVersion: version, values: values[id] ?? {} }))
        }
      })
    }
    return api.reviewCollectionAnnotationsApiUserCollectionsCollectionIdAnnotationsReviewPost({
      collectionId,
      annotationReviewRequest: {
        action: into.action,
        annotationIds: part.map(([id]) => id),
        expectedVersions: Object.fromEntries(part),
        tagId: into.tagId
      }
    })
  }

  /**
   * Sends `items` (each with the version it expects) into `into`; false when stopped because
   * the context changed (the answers are dropped then). `unchanged`: the selection still has
   * the members it had at the start; once it has not, the remaining parts are not sent.
   * `onSaved`: the answer of each part, for the values to undo.
   */
  async function send (collectionId: string, into: ReviewReport, items: SelectionEntry[], applies: () => boolean,
    unchanged: () => boolean, onSaved?: (result: AnnotationReviewResult) => void) {
    progress.value = 0
    const failures = (list: SelectionEntry[], message: string, uncertain = false) =>
      list.map(([id, version]) => ({ id, message, uncertain, version }))
    for (let i = 0; i < items.length; i += REVIEW_BATCH) {
      if (!applies()) return false
      if (!unchanged()) {
        into.notSent += items.length - i
        into.error = `Stopped because the selection changed; ${items.length - i} were not sent.`
        return true
      }
      const part = items.slice(i, i + REVIEW_BATCH)
      const expected = Object.fromEntries(part)
      try {
        const result = await request(collectionId, into, part)
        if (!applies()) return false
        onSaved?.(result)
        const versions = result.versions ?? {}
        const saved = result.succeeded ?? []
        into.saved.push(...saved)
        selection.noteVersions(Object.fromEntries(saved.filter(id => id in versions).map(id => [id, versions[id]!])))
        for (const f of result.failed ?? []) {
          const id = f.itemId
          if (!id) continue
          if (f.step === 'find_annotation') into.missing.push(id)
          else if (f.step === 'update_chunk_tags') into.unsynced.push(id)
          else if (f.step === 'edit_conflict') into.conflicts.push({ id, version: versions[id] ?? expected[id] ?? 0 })
          else into.failed.push({ id, message: f.message, uncertain: !!f.uncertain, version: expected[id] ?? 0 })
        }
      } catch (e) {
        if (!applies()) return false
        const status = errorStatus(e)
        if (status !== null && status < 500) {
          into.error = await apiErrorMessage(e, into.action === 'restore' ? 'The undo was refused.' : 'The review was refused.')
          into.failed.push(...failures(part, into.error ?? ''))
          into.notSent += items.length - i - part.length
          into.failed.push(...failures(items.slice(i + part.length), 'Not sent.'))
          return true
        }
        // A 5xx or lost answer: the part may have been applied.
        into.failed.push(...failures(part, 'No answer from the server.', true))
      }
      progress.value = Math.min(items.length, i + part.length)
    }
    return true
  }

  /** Re-derives the search references of `into.unsynced`, keeping the pairs still not
   * updated; false when stopped because the context changed. */
  async function sync (collectionId: string, into: ReviewReport, applies: () => boolean) {
    const pairs = [...new Set(into.unsynced)]
    const left: string[] = []
    for (let i = 0; i < pairs.length; i += SYNC_BATCH) {
      if (!applies()) return false
      const part = pairs.slice(i, i + SYNC_BATCH)
      try {
        const result = await api.syncCollectionAnnotationChunkTagsApiUserCollectionsCollectionIdAnnotationsChunkTagsSyncPost({
          collectionId,
          chunkTagSyncRequest: {
            pairs: part.map(pair => {
              const [chunkId = '', tagId = ''] = pair.split(':')
              return { chunkId, tagId }
            })
          }
        })
        if (!applies()) return false
        for (const f of result.failed ?? []) if (f.itemId) left.push(f.itemId)
      } catch (e) {
        if (!applies()) return false
        left.push(...part)
        into.error ??= await apiErrorMessage(e, 'Tag-filtered search could not be updated.')
      }
    }
    into.unsynced = left
    return true
  }

  /** The guards of a new run: its context still applies, and the selection is unchanged. */
  function startRun () {
    const mine = ++run
    const inScope = selection.captureScope()
    const inSession = captureSession()
    return {
      mine,
      applies: () => mine === run && inScope() && inSession(),
      unchanged: selection.captureMembership()
    }
  }

  /** Makes `change` the one to undo, or says why the last change cannot be undone. */
  function noteChange (change: UndoableChange | null, note: string | null = null) {
    if (change && change.items.length > REVIEW_BATCH) {
      undoable.value = null
      undoNote.value = `Changes of more than ${REVIEW_BATCH} annotations cannot be undone.`
      return
    }
    undoable.value = change?.items.length ? change : null
    undoNote.value = change?.items.length ? null : note
  }

  /** Collects the previous values of the annotations an answer changed, at their new versions. */
  function collectUndo (into: UndoItem[]) {
    return (result: AnnotationReviewResult) => {
      const versions = result.versions ?? {}
      for (const [id, values] of Object.entries(result.previous ?? {})) {
        const version = versions[id]
        if (version !== undefined && (result.succeeded ?? []).includes(id)) into.push({ id, version, values })
      }
    }
  }

  /**
   * Applies `action` to the annotations of the collection, each expected at its version;
   * returns the report, or null when the collection was left or the session ended meanwhile
   * (nothing more is sent then). Its changes become the ones to undo.
   */
  async function review (collectionId: string, action: ReviewAction, items: SelectionEntry[],
    tagId: string | null = null): Promise<ReviewReport | null> {
    const targets = [...new Map(items)]
    const { mine, applies, unchanged } = startRun()
    const next = emptyReport(action, tagId, targets.length)
    const changed: UndoItem[] = []
    target.value = targets.length
    running.value = true
    try {
      const sent = await send(collectionId, next, targets, applies, unchanged, collectUndo(changed))
      // Also when stopped: what was saved is the last change. One that changed nothing
      // leaves the change before it to undo.
      if (applies() && (action === ReviewAction.delete ? next.saved.length : changed.length)) noteUndo(action, changed)
      if (!sent) return null
      next.unsynced = [...new Set(next.unsynced)]
      report.value = next
      return next
    } finally {
      if (mine === run) running.value = false
    }
  }

  function noteUndo (action: ReviewAction, changed: UndoItem[]) {
    if (action === ReviewAction.delete) noteChange(null, 'Deleted annotations cannot be restored.')
    else noteChange({ kind: action, items: changed })
  }

  /**
   * Undoes the last change: restores the previous values of its annotations that still have
   * the version it left; returns the report (action `restore`), or null when nothing is to
   * undo or the context changed meanwhile.
   */
  async function undo (collectionId: string): Promise<ReviewReport | null> {
    const change = undoable.value
    if (!change || running.value) return null
    const { mine, applies } = startRun()
    const next = emptyReport('restore', null, change.items.length)
    next.values = Object.fromEntries(change.items.map(i => [i.id, i.values]))
    target.value = change.items.length
    running.value = true
    try {
      // Undone once: the items not restored are reported (and failed ones retried) instead.
      const sent = await send(collectionId, next, change.items.map(i => [i.id, i.version]), applies, () => true)
      if (!sent) return null
      if (undoable.value === change) noteChange(null)
      next.unsynced = [...new Set(next.unsynced)]
      report.value = next
      return next
    } finally {
      if (mine === run) running.value = false
    }
  }

  /** Sends the failed and uncertain items of the last report again and repairs its
   * search references that were not updated. */
  async function retry (collectionId: string): Promise<ReviewReport | null> {
    const last = report.value
    if (!last || (!last.failed.length && !last.unsynced.length)) return last
    const { mine, applies, unchanged } = startRun()
    const next: ReviewReport = {
      ...last,
      failed: [],
      notSent: 0,
      error: null,
      saved: [...last.saved],
      conflicts: [...last.conflicts],
      missing: [...last.missing],
      unsynced: [...last.unsynced]
    }
    target.value = last.failed.length
    running.value = true
    const changed: UndoItem[] = []
    try {
      const sent = await send(collectionId, next, last.failed.map(f => [f.id, f.version]), applies, unchanged,
        collectUndo(changed))
      // A retried review adds what it saved to the change to undo.
      if (applies() && last.action !== 'restore' && changed.length) {
        const kept = undoable.value?.kind === last.action ? undoable.value.items : []
        noteUndo(last.action, [...kept, ...changed])
      }
      if (!sent) return null
      if (!await sync(collectionId, next, applies)) return null
      report.value = next
      return next
    } finally {
      if (mine === run) running.value = false
    }
  }

  function dismiss () {
    report.value = null
  }

  /** Forgets the report and the undo, and stops a running action (sign-out, another collection). */
  function clear () {
    run++
    running.value = false
    progress.value = 0
    report.value = null
    undoable.value = null
    undoNote.value = null
  }

  return { running, progress, target, report, undoable, undoNote, review, retry, undo, noteChange, dismiss, clear }
})
