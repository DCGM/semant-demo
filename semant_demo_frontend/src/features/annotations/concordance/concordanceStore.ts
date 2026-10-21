import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'
import {
  AnnotationSort, SpanType, type AnnotatedDocument, type AnnotationPage
} from 'src/generated/api'
import { apiErrorMessage, captureSession, createContextGuard, createScope, errorStatus, isAbortError, useApi } from 'src/shared/api'
import { MAX_SELECTION, useAnnotationSelectionStore } from '../annotationSelectionStore'
import { useAnnotationReviewStore } from './annotationReviewStore'

/** Rows per page of the concordance. */
export const PAGE_SIZE = 50

/** What the concordance shows; every change goes back to the first page. */
export interface ConcordanceFilters {
  tagIds: string[]
  /** `pos` (manual or approved) and `auto` (proposals) by default; `neg` only when chosen. */
  types: SpanType[]
  /** Words that must each occur in the annotated text. */
  text: string
  documentIds: string[]
  yearFrom: number | null
  yearTo: number | null
  sort: AnnotationSort
}

export function defaultFilters (): ConcordanceFilters {
  return {
    tagIds: [],
    types: [SpanType.pos, SpanType.auto],
    text: '',
    documentIds: [],
    yearFrom: null,
    yearTo: null,
    sort: AnnotationSort.document
  }
}

function failure (e: unknown, what: string): string {
  const status = errorStatus(e)
  if (status === 404) return 'This collection is not available to you.'
  if (status === 400) return `The ${what} could not be read with these filters; narrow them and try again.`
  console.error(`Loading the ${what} failed`, e)
  return `Failed to load the ${what}.`
}

/** The request body of the concordance filters for resolving annotation ids. */
function idsRequest (f: ConcordanceFilters, within?: string[]) {
  return {
    tagIds: f.tagIds.length ? f.tagIds : null,
    types: f.types,
    q: f.text.trim() || null,
    documentIds: f.documentIds.length ? f.documentIds : null,
    yearFrom: f.yearFrom,
    yearTo: f.yearTo,
    within: within ?? null
  }
}

/**
 * The collection's annotation workspace (#329): the concordance query, its current page
 * and the scroll position; the checked and focused annotations are the workspace selection
 * (`annotationSelectionStore`, #459), which this store also tells which selected
 * annotations the current filters show. It belongs to one collection of the signed-in user
 * and outlives the page, so leaving for a document and coming back keeps filters, page,
 * selection and position. Opening another collection starts afresh; signing out clears it
 * (`app/session.ts`).
 *
 * Each query is a context: a newer query, another collection or a sign-out aborts it and
 * drops its late answer. A failed read is reported as an error, never as an empty result.
 */
export const useConcordanceStore = defineStore('concordance', () => {
  const api = useApi().default
  const scope = createScope()
  const rowRequests = createContextGuard()
  const documentRequests = createContextGuard()
  const shownRequests = createContextGuard()
  const resolveRequests = createContextGuard()
  const selection = useAnnotationSelectionStore()
  let rowAbort: AbortController | null = null
  let documentAbort: AbortController | null = null

  const collectionId = ref<string | null>(null)
  const filters = ref<ConcordanceFilters>(defaultFilters())
  const offset = ref(0)
  const page = shallowRef<AnnotationPage | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const documents = shallowRef<AnnotatedDocument[]>([])
  const documentsError = ref<string | null>(null)
  /** Annotations known to match the current filters (listed, resolved, or the selected
   * ones the filters show); selected annotations of `known` not in it are hidden, or no
   * longer exist. */
  const shown = ref<Set<string>>(new Set())
  /** Ids whose membership in `shown` is known for the current filters. */
  const known = ref<Set<string>>(new Set())
  const shownError = ref<string | null>(null)
  /** "Select all matches" is resolving the current filters. */
  const resolving = ref(false)
  const scrollY = ref(0)
  /** The query and offset of `page`. */
  let pageKey: string | null = null

  const rows = computed(() => page.value?.rows ?? [])
  const total = computed(() => page.value?.total ?? 0)
  /** Selected annotations the current filters do not show (or that no longer exist);
   * null while that is not known for the current selection. */
  const hiddenSelected = computed<number | null>(() => {
    const ids = selection.ids
    if ([...ids].some(id => !known.value.has(id) && !shown.value.has(id))) return null
    return [...ids].filter(id => !shown.value.has(id)).length
  })

  function stop () {
    rowAbort?.abort()
    documentAbort?.abort()
    rowAbort = documentAbort = null
    rowRequests.enter()
    documentRequests.enter()
    shownRequests.enter()
    loading.value = false
    stopResolving()
  }

  /** Drops a running "select all matches" (its filters are no longer the current ones). */
  function stopResolving () {
    resolveRequests.enter()
    resolving.value = false
  }

  function reset () {
    stop()
    filters.value = defaultFilters()
    offset.value = 0
    page.value = null
    error.value = null
    documents.value = []
    documentsError.value = null
    shown.value = new Set()
    known.value = new Set()
    shownError.value = null
    pageKey = null
    scrollY.value = 0
  }

  /** Brings the focused row up to date with a newly read page of the query `key`. */
  function reconcileFocused (result: AnnotationPage, key: string, refresh: boolean) {
    const row = selection.focused
    if (!row) return
    const fresh = result.rows.find(r => r.id === row.id)
    if (fresh) selection.focus(fresh)
    else if ((refresh || key === pageKey) && page.value?.rows.some(r => r.id === row.id)) selection.focusedGone = true
  }

  /** Shows the collection's workspace: as it was left, or a new one for another collection. */
  async function open (id: string) {
    if (scope.enter(id)) {
      reset()
      collectionId.value = id
      useAnnotationReviewStore().clear()
    }
    selection.enter(id)
    await Promise.all([load(), loadDocuments(), loadShown()])
  }

  /** Reads the current page again (also after returning, so edits made elsewhere show). */
  function load () {
    return read(false)
  }

  /** `refresh`: the page is read again at another offset because rows were removed. */
  async function read (refresh: boolean) {
    const id = collectionId.value
    if (!id) return
    rowAbort?.abort()
    rowRequests.enter()
    const isCurrent = rowRequests.capture()
    const inScope = scope.capture()
    const inSession = captureSession()
    const applies = () => isCurrent() && inScope() && inSession()
    const controller = new AbortController()
    rowAbort = controller
    const f = filters.value
    const key = JSON.stringify([f, offset.value])
    loading.value = true
    error.value = null
    try {
      const result = await api.listCollectionAnnotationsApiUserCollectionsCollectionIdAnnotationsGet({
        collectionId: id,
        tagId: f.tagIds.length ? f.tagIds : undefined,
        type: f.types,
        q: f.text.trim() || undefined,
        documentId: f.documentIds.length ? f.documentIds : undefined,
        yearFrom: f.yearFrom ?? undefined,
        yearTo: f.yearTo ?? undefined,
        sort: f.sort,
        limit: PAGE_SIZE,
        offset: offset.value
      }, { signal: controller.signal })
      if (!applies()) return
      // Rows removed meanwhile (e.g. deleted in the document view) leave the page empty.
      if (!result.rows.length && result.total > 0 && offset.value > 0) {
        offset.value = Math.max(0, Math.floor((result.total - 1) / PAGE_SIZE) * PAGE_SIZE)
        void read(refresh || key === pageKey)
        return
      }
      reconcileFocused(result, key, refresh)
      page.value = result
      pageKey = key
      // Rows on the page match the filters: checking one never makes it hidden.
      noteShown(result.rows.map(r => r.id))
    } catch (e) {
      if (!applies() || isAbortError(e)) return
      page.value = null
      error.value = failure(e, 'annotations')
    } finally {
      if (applies()) {
        loading.value = false
        rowAbort = null
      }
    }
  }

  /** The annotated documents for the source and year filters (of the chosen tags and types). */
  async function loadDocuments () {
    const id = collectionId.value
    if (!id) return
    documentAbort?.abort()
    documentRequests.enter()
    const isCurrent = documentRequests.capture()
    const inScope = scope.capture()
    const inSession = captureSession()
    const applies = () => isCurrent() && inScope() && inSession()
    const controller = new AbortController()
    documentAbort = controller
    documentsError.value = null
    try {
      const result = await api.listAnnotatedDocumentsApiUserCollectionsCollectionIdAnnotationsDocumentsGet({
        collectionId: id,
        tagId: filters.value.tagIds.length ? filters.value.tagIds : undefined,
        type: filters.value.types
      }, { signal: controller.signal })
      if (applies()) documents.value = result
    } catch (e) {
      if (!applies() || isAbortError(e)) return
      documents.value = []
      documentsError.value = failure(e, 'documents')
    } finally {
      if (applies()) documentAbort = null
    }
  }

  /** Marks ids as matching the current filters (they were just listed or resolved for them). */
  function noteShown (ids: string[]) {
    shown.value = new Set([...shown.value, ...ids])
    known.value = new Set([...known.value, ...ids])
  }

  /** Asks which selected annotations the current filters show (after the filters, the
   * selection's members or the annotations changed). */
  async function loadShown () {
    const id = collectionId.value
    shownRequests.enter()
    const ids = [...selection.ids]
    shownError.value = null
    if (!id || !ids.length) {
      shown.value = new Set()
      known.value = new Set()
      return
    }
    const isCurrent = shownRequests.capture()
    const inScope = scope.capture()
    const inSession = captureSession()
    const applies = () => isCurrent() && inScope() && inSession()
    known.value = new Set()
    try {
      const result = await api.resolveCollectionAnnotationIdsApiUserCollectionsCollectionIdAnnotationsIdsPost({
        collectionId: id, annotationIdsRequest: idsRequest(filters.value, ids)
      })
      if (!applies()) return
      // Ids noted meanwhile (rows read, members added) keep what is known about them.
      const asked = new Set(ids)
      shown.value = new Set([...[...shown.value].filter(i => !asked.has(i)), ...result.ids])
      known.value = new Set([...known.value, ...ids])
    } catch (e) {
      if (!applies()) return
      shownError.value = failure(e, 'selection')
    }
  }

  /**
   * Adds every annotation matching the current filters to the selection, as the ids the
   * server resolves now: later filter changes do not widen it. Returns a message when
   * nothing was added (too many matches, or the selection would exceed its limit).
   */
  async function selectAllMatches (): Promise<string | null> {
    const id = collectionId.value
    if (!id) return null
    resolveRequests.enter()
    const isCurrent = resolveRequests.capture()
    const inScope = scope.capture()
    const inSession = captureSession()
    const applies = () => isCurrent() && inScope() && inSession()
    resolving.value = true
    try {
      const result = await api.resolveCollectionAnnotationIdsApiUserCollectionsCollectionIdAnnotationsIdsPost({
        collectionId: id, annotationIdsRequest: idsRequest(filters.value)
      })
      if (!applies()) return null
      if (!selection.add(result.ids)) {
        return `The selection can hold at most ${MAX_SELECTION} annotations; clear it or narrow the filters.`
      }
      // All matches are known now: every other member is hidden by the filters. This
      // supersedes a pending answer about which members the filters show.
      shownRequests.enter()
      shownError.value = null
      shown.value = new Set(result.ids)
      known.value = new Set(selection.ids)
      return null
    } catch (e) {
      if (!applies()) return null
      return errorStatus(e) === 400
        ? await apiErrorMessage(e, 'Too many annotations match; narrow the filters.')
        : failure(e, 'matching annotations')
    } finally {
      if (isCurrent()) resolving.value = false
    }
  }

  /** Drops the selected annotations the current filters do not show. */
  function deselectHidden () {
    if (hiddenSelected.value === null) return
    selection.retain(shown.value)
  }

  /** Changes the query and shows its first page. */
  async function setFilters (change: Partial<ConcordanceFilters>) {
    const before = filters.value
    filters.value = { ...before, ...change }
    offset.value = 0
    stopResolving()
    shown.value = new Set()
    known.value = new Set()
    const facetsChanged = 'tagIds' in change || 'types' in change
    await Promise.all([load(), facetsChanged ? loadDocuments() : Promise.resolve(), loadShown()])
  }

  async function resetFilters () {
    filters.value = defaultFilters()
    offset.value = 0
    stopResolving()
    shown.value = new Set()
    known.value = new Set()
    await Promise.all([load(), loadDocuments(), loadShown()])
  }

  async function goTo (nextOffset: number) {
    if (nextOffset < 0 || (page.value && nextOffset >= page.value.total)) return
    offset.value = nextOffset
    scrollY.value = 0
    await load()
  }

  /** Checks or unchecks the rows of the current page; false when the selection would exceed its limit. */
  function setPageSelected (value: boolean): boolean {
    const ids = rows.value.map(r => r.id)
    if (!value) {
      selection.remove(ids)
      return true
    }
    return selection.add(ids)
  }

  /** Forgets everything (sign-out, another account). */
  function clear () {
    scope.reset()
    reset()
    collectionId.value = null
    selection.clear()
    useAnnotationReviewStore().clear()
  }

  return {
    collectionId,
    filters,
    offset,
    page,
    rows,
    total,
    loading,
    error,
    documents,
    documentsError,
    shown,
    shownError,
    hiddenSelected,
    resolving,
    scrollY,
    open,
    load,
    loadDocuments,
    loadShown,
    selectAllMatches,
    deselectHidden,
    setFilters,
    resetFilters,
    goTo,
    setPageSelected,
    clear
  }
})
