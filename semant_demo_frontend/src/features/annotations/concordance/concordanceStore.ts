import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'
import {
  AnnotationSort, SpanType, type AnnotatedDocument, type AnnotationListRow, type AnnotationPage
} from 'src/generated/api'
import { captureSession, createContextGuard, createScope, errorStatus, isAbortError, useApi } from 'src/shared/api'

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

/**
 * The collection's annotation workspace (#329): the concordance query, its current page,
 * the checked rows, the row whose source is open and the scroll position. It belongs to
 * one collection of the signed-in user and outlives the page, so leaving for a document
 * and coming back keeps filters, page, selection and position. Opening another collection
 * starts afresh; signing out clears it (`app/session.ts`).
 *
 * Each query is a context: a newer query, another collection or a sign-out aborts it and
 * drops its late answer. A failed read is reported as an error, never as an empty result.
 */
export const useConcordanceStore = defineStore('concordance', () => {
  const api = useApi().default
  const scope = createScope()
  const rowRequests = createContextGuard()
  const documentRequests = createContextGuard()
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
  /** Checked rows by id; kept across pages and filters (actions on them: #330). */
  const selected = ref<Set<string>>(new Set())
  /** The row whose source context is open, as the latest page that lists it shows it. */
  const focused = shallowRef<AnnotationListRow | null>(null)
  /** The focused row left its page when the page was read again: it was deleted, or an
   * edit took it out of the filters or moved it to another page; `focused` is outdated. */
  const focusedGone = ref(false)
  const scrollY = ref(0)
  /** The query and offset of `page`. */
  let pageKey: string | null = null

  const rows = computed(() => page.value?.rows ?? [])
  const total = computed(() => page.value?.total ?? 0)

  function stop () {
    rowAbort?.abort()
    documentAbort?.abort()
    rowAbort = documentAbort = null
    rowRequests.enter()
    documentRequests.enter()
    loading.value = false
  }

  function reset () {
    stop()
    filters.value = defaultFilters()
    offset.value = 0
    page.value = null
    error.value = null
    documents.value = []
    documentsError.value = null
    selected.value = new Set()
    focused.value = null
    focusedGone.value = false
    pageKey = null
    scrollY.value = 0
  }

  function focus (row: AnnotationListRow | null) {
    focused.value = row
    focusedGone.value = false
  }

  /** Brings the focused row up to date with a newly read page of the query `key`. */
  function reconcileFocused (result: AnnotationPage, key: string, refresh: boolean) {
    const row = focused.value
    if (!row) return
    const fresh = result.rows.find(r => r.id === row.id)
    if (fresh) focus(fresh)
    else if ((refresh || key === pageKey) && page.value?.rows.some(r => r.id === row.id)) focusedGone.value = true
  }

  /** Shows the collection's workspace: as it was left, or a new one for another collection. */
  async function open (id: string) {
    if (scope.enter(id)) {
      reset()
      collectionId.value = id
    }
    await Promise.all([load(), loadDocuments()])
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

  /** Changes the query and shows its first page. */
  async function setFilters (change: Partial<ConcordanceFilters>) {
    const before = filters.value
    filters.value = { ...before, ...change }
    offset.value = 0
    const facetsChanged = 'tagIds' in change || 'types' in change
    await Promise.all([load(), facetsChanged ? loadDocuments() : Promise.resolve()])
  }

  async function resetFilters () {
    filters.value = defaultFilters()
    offset.value = 0
    await Promise.all([load(), loadDocuments()])
  }

  async function goTo (nextOffset: number) {
    if (nextOffset < 0 || (page.value && nextOffset >= page.value.total)) return
    offset.value = nextOffset
    scrollY.value = 0
    await load()
  }

  function toggleSelected (id: string, value?: boolean) {
    const next = new Set(selected.value)
    if (value ?? !next.has(id)) next.add(id)
    else next.delete(id)
    selected.value = next
  }

  function setPageSelected (value: boolean) {
    const next = new Set(selected.value)
    rows.value.forEach((r) => value ? next.add(r.id) : next.delete(r.id))
    selected.value = next
  }

  function clearSelection () {
    selected.value = new Set()
  }

  /** Forgets everything (sign-out, another account). */
  function clear () {
    scope.reset()
    reset()
    collectionId.value = null
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
    selected,
    focused,
    focusedGone,
    scrollY,
    focus,
    open,
    load,
    loadDocuments,
    setFilters,
    resetFilters,
    goTo,
    toggleSelected,
    setPageSelected,
    clearSelection,
    clear
  }
})
