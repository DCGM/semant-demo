import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'
import { ReviewAction } from 'src/generated/api'
import { apiErrorMessage, captureSession, errorStatus, useApi } from 'src/shared/api'
import { useAnnotationSelectionStore } from '../annotationSelectionStore'

/** Annotations sent per review request (the backend accepts at most 200). */
export const REVIEW_BATCH = 200

/** An annotation whose review write did not succeed, or may not have. */
export interface ReviewFailure {
  id: string
  message: string
  /** The write timed out or its answer was lost: it may have been applied. */
  uncertain: boolean
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
  /** Not annotations of the collection (any more): deleted meanwhile, or never there. */
  missing: string[]
  /** Saved changes that tag-filtered search does not reflect yet (repeating the action updates it). */
  searchNotUpdated: number
  /** Targets not sent because a request was refused (e.g. access was revoked). */
  notSent: number
  /** Why the action stopped early. */
  error: string | null
}

/**
 * Review actions of the annotation workspace (#459): approve, reject, retag or delete a
 * fixed list of annotations, sent in parts of `REVIEW_BATCH`. The targets are resolved when
 * the action starts (the explicit selection or one row), so later filter changes never
 * widen it. Writes are best effort and reported per annotation; nothing is rolled back.
 * Retrying sends only failed and uncertain items.
 *
 * Leaving the collection or signing out stops sending further parts and drops the report;
 * writes already sent are kept by the backend. A refused part (4xx) stops the action; a
 * lost answer marks its part uncertain and continues with the next.
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
    return { action, tagId, target, saved: [], failed: [], missing: [], searchNotUpdated: 0, notSent: 0, error: null }
  }

  /** Sends `ids` into `into`; false when stopped because the context changed. */
  async function send (collectionId: string, into: ReviewReport, ids: string[], applies: () => boolean) {
    progress.value = 0
    for (let i = 0; i < ids.length; i += REVIEW_BATCH) {
      if (!applies()) return false
      const part = ids.slice(i, i + REVIEW_BATCH)
      try {
        const result = await api.reviewCollectionAnnotationsApiUserCollectionsCollectionIdAnnotationsReviewPost({
          collectionId,
          annotationReviewRequest: { action: into.action, annotationIds: part, tagId: into.tagId }
        })
        if (!applies()) return false
        into.saved.push(...(result.succeeded ?? []))
        for (const f of result.failed ?? []) {
          if (f.step === 'find_annotation' && f.itemId) into.missing.push(f.itemId)
          else if (f.step === 'update_chunk_tags') into.searchNotUpdated++
          else if (f.itemId) into.failed.push({ id: f.itemId, message: f.message, uncertain: !!f.uncertain })
        }
      } catch (e) {
        if (!applies()) return false
        const status = errorStatus(e)
        if (status !== null && status < 500) {
          into.error = await apiErrorMessage(e, 'The review was refused.')
          into.failed.push(...part.map(id => ({ id, message: into.error ?? '', uncertain: false })))
          into.notSent += ids.length - i - part.length
          into.failed.push(...ids.slice(i + part.length).map(id => ({ id, message: 'Not sent.', uncertain: false })))
          return true
        }
        // A 5xx or lost answer: the part may have been applied.
        into.failed.push(...part.map(id => ({ id, message: 'No answer from the server.', uncertain: true })))
      }
      progress.value = Math.min(ids.length, i + part.length)
    }
    return true
  }

  /**
   * Applies `action` to `ids` of the collection; returns the report, or null when the
   * collection was left or the session ended meanwhile (nothing more is sent then).
   */
  async function review (collectionId: string, action: ReviewAction, ids: string[],
    tagId: string | null = null): Promise<ReviewReport | null> {
    const targets = [...new Set(ids)]
    const mine = ++run
    const inScope = selection.captureScope()
    const inSession = captureSession()
    const applies = () => mine === run && inScope() && inSession()
    const next = emptyReport(action, tagId, targets.length)
    target.value = targets.length
    running.value = true
    try {
      if (!await send(collectionId, next, targets, applies)) return null
      report.value = next
      return next
    } finally {
      if (mine === run) running.value = false
    }
  }

  /** Sends the failed and uncertain items of the last report again. */
  async function retry (collectionId: string): Promise<ReviewReport | null> {
    const last = report.value
    if (!last || !last.failed.length) return last
    const mine = ++run
    const inScope = selection.captureScope()
    const inSession = captureSession()
    const applies = () => mine === run && inScope() && inSession()
    const next: ReviewReport = { ...last, failed: [], notSent: 0, error: null, saved: [...last.saved], missing: [...last.missing] }
    target.value = last.failed.length
    running.value = true
    try {
      if (!await send(collectionId, next, last.failed.map(f => f.id), applies)) return null
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
