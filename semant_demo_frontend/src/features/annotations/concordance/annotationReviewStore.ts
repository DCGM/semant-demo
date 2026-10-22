import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'
import { ReviewAction } from 'src/generated/api'
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

/** What one review action (and its retries) did, per annotation. */
export interface ReviewReport {
  action: ReviewAction
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
 * Leaving the collection or signing out stops sending further parts and drops the report;
 * writes already sent are kept by the backend. A change of the selection's members stops
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
  let run = 0

  function emptyReport (action: ReviewAction, tagId: string | null, target: number): ReviewReport {
    return { action, tagId, target, saved: [], failed: [], conflicts: [], missing: [], unsynced: [], notSent: 0, error: null }
  }

  /**
   * Sends `items` (each with the version it expects) into `into`; false when stopped because
   * the context changed (the answers are dropped then). `unchanged`: the selection still has
   * the members it had at the start; once it has not, the remaining parts are not sent.
   */
  async function send (collectionId: string, into: ReviewReport, items: SelectionEntry[], applies: () => boolean,
    unchanged: () => boolean) {
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
        const result = await api.reviewCollectionAnnotationsApiUserCollectionsCollectionIdAnnotationsReviewPost({
          collectionId,
          annotationReviewRequest: {
            action: into.action, annotationIds: part.map(([id]) => id), expectedVersions: expected, tagId: into.tagId
          }
        })
        if (!applies()) return false
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
          into.error = await apiErrorMessage(e, 'The review was refused.')
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

  /**
   * Applies `action` to the annotations of the collection, each expected at its version;
   * returns the report, or null when the collection was left or the session ended meanwhile
   * (nothing more is sent then).
   */
  async function review (collectionId: string, action: ReviewAction, items: SelectionEntry[],
    tagId: string | null = null): Promise<ReviewReport | null> {
    const targets = [...new Map(items)]
    const { mine, applies, unchanged } = startRun()
    const next = emptyReport(action, tagId, targets.length)
    target.value = targets.length
    running.value = true
    try {
      if (!await send(collectionId, next, targets, applies, unchanged)) return null
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
    try {
      if (!await send(collectionId, next, last.failed.map(f => [f.id, f.version]), applies, unchanged)) return null
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

  /** Forgets the report and stops a running action (sign-out, another collection). */
  function clear () {
    run++
    running.value = false
    progress.value = 0
    report.value = null
  }

  return { running, progress, target, report, review, retry, dismiss, clear }
})
