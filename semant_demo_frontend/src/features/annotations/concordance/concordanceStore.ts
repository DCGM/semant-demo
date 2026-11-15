import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'
import {
  AnnotationSort, RetrievalMode, SpanType, TextScope, type AnnotatedDocument, type AnnotationListRow, type AnnotationPage,
  type AnnotationRanking, type AttributeAssignResult, type CollectionPerson, type DocumentFilters
} from 'src/generated/api'
import { apiErrorMessage, captureSession, createContextGuard, createScope, errorStatus, isAbortError, useApi } from 'src/shared/api'
import { MAX_SELECTION, useAnnotationSelectionStore } from '../annotationSelectionStore'
import { useAttributeAssignStore } from 'src/features/attributes/attributeAssignStore'
import { useAnnotationReviewStore } from './annotationReviewStore'

/** Rows per page of the concordance. */
export const PAGE_SIZE = 50

/** The choices of `k` of a ranked query (#664); the server allows 1–500. */
export const TOP_K_OPTIONS = [20, 50, 100, 200, 500]
export const DEFAULT_TOP_K = 100

/** What the concordance shows; every change goes back to the first page. */
export interface ConcordanceFilters {
  tagIds: string[]
  /** `pos` (manual or approved) and `auto` (proposals) by default; `neg` only when chosen. */
  types: SpanType[]
  /** Words that must each occur inside a word of a field of `textScope`, ignoring case (#663). */
  text: string
  /** Where the words of `text` must occur: the annotated text, its context, or either. */
  textScope: TextScope
  documentIds: string[]
  /** The shared document filters (#526): publication years, title, library, document language;
   * normalized (`normalizeDocumentFilters`), so "no filter" is always `{}`. */
  documentFilters: DocumentFilters
  /** Accepted attribute values, as `<attribute id>:<value id>`: values of one attribute match
   * any, different attributes all (ADR 0011). */
  attributeValues: string[]
  /** Attribute ids the annotations must hold no value of. */
  attributeUnassigned: string[]
  /** Lexical mode only; ranked results are in relevance order. */
  sort: AnnotationSort
  /** Reverses `sort` (missing titles, years and texts stay last). */
  descending: boolean
  /** Every match (`lexical`) or a ranked top `k` (#664): by meaning of `text` (`semantic`),
   * meaning and words of `text` (`hybrid`), or like `similarTo` (`similar`; `text` then stays a
   * lexical filter). */
  mode: RetrievalMode
  k: number
  /** Mode `similar`: the source annotation, as listed when it was chosen. */
  similarTo: AnnotationListRow | null
  /** Mode `similar`: rank the source too. */
  includeSource: boolean
}

/** The modes that rank by the query text (it is then no lexical filter). */
export function ranksText (mode: RetrievalMode): boolean {
  return mode === RetrievalMode.semantic || mode === RetrievalMode.hybrid
}

/** The filter change that switches to `mode` (never `similar`, which needs a source). */
export function modeChange (mode: RetrievalMode): Partial<ConcordanceFilters> {
  return { mode, similarTo: null, includeSource: false }
}

/** The filter change of Find similar from `row`, keeping the other filters; a text that ranked
 * by meaning is dropped, since in mode `similar` it would filter by words. */
export function similarChange (f: ConcordanceFilters, row: AnnotationListRow): Partial<ConcordanceFilters> {
  return { mode: RetrievalMode.similar, similarTo: row, includeSource: false, ...(ranksText(f.mode) ? { text: '' } : {}) }
}

/** The ranking of the filters for the API; none in lexical mode. */
function ranking (f: ConcordanceFilters): AnnotationRanking | undefined {
  if (f.mode === RetrievalMode.lexical) return undefined
  return {
    mode: f.mode,
    k: f.k,
    similarTo: f.mode === RetrievalMode.similar ? f.similarTo?.id ?? null : null,
    includeSource: f.mode === RetrievalMode.similar && f.includeSource
  }
}

export function defaultFilters (): ConcordanceFilters {
  return {
    tagIds: [],
    types: [SpanType.pos, SpanType.auto],
    text: '',
    textScope: TextScope.annotation,
    documentIds: [],
    documentFilters: {},
    attributeValues: [],
    attributeUnassigned: [],
    sort: AnnotationSort.document,
    descending: false,
    mode: RetrievalMode.lexical,
    k: DEFAULT_TOP_K,
    similarTo: null,
    includeSource: false
  }
}

/** The document filters without empty values, so equal filters compare equal. */
export function normalizeDocumentFilters (f: DocumentFilters): DocumentFilters {
  const result: DocumentFilters = {}
  if (f.yearMin != null) result.yearMin = f.yearMin
  if (f.yearMax != null) result.yearMax = f.yearMax
  if (f.titleContains?.length) result.titleContains = [...f.titleContains]
  if (f.libraries?.length) result.libraries = [...f.libraries]
  if (f.languages?.length) result.languages = [...f.languages]
  return result
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
    textScope: f.textScope,
    documentIds: f.documentIds.length ? f.documentIds : null,
    documentFilters: normalizeDocumentFilters(f.documentFilters),
    attributeValues: f.attributeValues.length ? f.attributeValues : undefined,
    attributeUnassigned: f.attributeUnassigned.length ? f.attributeUnassigned : undefined,
    within: within ?? null,
    ranking: ranking(f)
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
  /** The collection's owner and members, to name who created or changed annotations (#460). */
  const people = shallowRef<CollectionPerson[]>([])
  const scrollY = ref(0)
  /** The attributes whose values the rows show in columns of their own (none by default),
   * in any order (they are shown in the collection's order); a view setting, not a filter. */
  const shownAttributeIds = ref<string[]>([])
  /** The query and offset of `page`. */
  let pageKey: string | null = null

  const rows = computed(() => page.value?.rows ?? [])
  /** A ranked mode that ranks by the text, without one: nothing is read until it is entered. */
  const needsText = computed(() => ranksText(filters.value.mode) && !filters.value.text.trim())
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
    people.value = []
    shownAttributeIds.value = []
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

  /**
   * Reads the focused annotation as it is now, whatever the filters, and keeps it focused
   * (a review of it was refused because someone changed it, possibly out of the filters;
   * #460). False when it no longer exists, another one is focused meanwhile, or reading failed.
   */
  async function readFocused (): Promise<boolean> {
    const id = collectionId.value
    const row = selection.focused
    if (!id || !row) return false
    const inScope = scope.capture()
    const inSession = captureSession()
    try {
      const result = await api.listCollectionAnnotationsApiUserCollectionsCollectionIdAnnotationsGet({
        collectionId: id, annotationId: [row.id], type: Object.values(SpanType), limit: 1
      })
      const fresh = result.rows[0]
      if (!fresh || !inScope() || !inSession() || selection.focused?.id !== row.id) return false
      selection.focus(fresh)
      return true
    } catch (e) {
      console.error('Reading the annotation failed', e)
      return false
    }
  }

  /** Shows the collection's workspace: as it was left, or a new one for another collection. */
  async function open (id: string) {
    if (scope.enter(id)) {
      reset()
      collectionId.value = id
      useAnnotationReviewStore().clear()
      useAttributeAssignStore().clear()
    }
    selection.enter(id)
    // Names only label provenance: the workspace does not wait for them.
    void loadPeople()
    await Promise.all([load(), loadDocuments(), loadShown()])
  }

  /** The collection's owner and members; without them actors show as "a former member". */
  async function loadPeople () {
    const id = collectionId.value
    if (!id) return
    const inScope = scope.capture()
    const inSession = captureSession()
    try {
      const result = await api.getCollectionPeopleApiUserCollectionsCollectionIdPeopleGet({ collectionId: id })
      if (inScope() && inSession()) people.value = result
    } catch (e) {
      console.error('Loading the collection members failed', e)
    }
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
    error.value = null
    if (needsText.value) {
      page.value = null
      pageKey = key
      loading.value = false
      rowAbort = null
      return
    }
    const ranked = ranking(f)
    loading.value = true
    try {
      const result = await api.listCollectionAnnotationsApiUserCollectionsCollectionIdAnnotationsGet({
        collectionId: id,
        tagId: f.tagIds.length ? f.tagIds : undefined,
        type: f.types,
        q: f.text.trim() || undefined,
        textScope: f.text.trim() && f.mode !== RetrievalMode.semantic ? f.textScope : undefined,
        documentId: f.documentIds.length ? f.documentIds : undefined,
        yearMin: f.documentFilters.yearMin ?? undefined,
        yearMax: f.documentFilters.yearMax ?? undefined,
        titleContains: f.documentFilters.titleContains?.length ? f.documentFilters.titleContains : undefined,
        libraries: f.documentFilters.libraries?.length ? f.documentFilters.libraries : undefined,
        languages: f.documentFilters.languages?.length ? f.documentFilters.languages : undefined,
        attribute: f.attributeValues.length ? f.attributeValues : undefined,
        unassigned: f.attributeUnassigned.length ? f.attributeUnassigned : undefined,
        sort: ranked ? undefined : f.sort,
        descending: !ranked && f.descending ? true : undefined,
        mode: ranked?.mode,
        k: ranked?.k,
        similarTo: ranked?.similarTo ?? undefined,
        includeSource: ranked?.includeSource || undefined,
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
      const status = errorStatus(e)
      // A ranked query is refused with a message of its own: no vector of the source (400), no
      // embedding service (503).
      const message = ranked && (status === 400 || status === 503)
        ? await apiErrorMessage(e, 'Search by meaning is not available now.')
        : failure(e, 'annotations')
      if (applies()) error.value = message
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
    if (needsText.value) { // nothing is shown until the text is entered
      shown.value = new Set()
      known.value = new Set(ids)
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
   * Adds every annotation matching the current filters to the selection, as the ids (and
   * versions) the server resolves now: later filter changes do not widen it. In a ranked mode
   * exactly the top `k` (#664), never every match of the filters. Returns a message when
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
      if (!selection.add(result.ids.map(i => [i, result.versions?.[i] ?? 0] as const), result.attributeVersions ?? {})) {
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
    if (change.documentFilters) filters.value.documentFilters = normalizeDocumentFilters(change.documentFilters)
    offset.value = 0
    stopResolving()
    shown.value = new Set()
    known.value = new Set()
    const facetsChanged = 'tagIds' in change || 'types' in change
    await Promise.all([load(), facetsChanged ? loadDocuments() : Promise.resolve(), loadShown()])
  }

  /** Lists the annotations most similar to `row`, within the current filters (#664). */
  async function findSimilar (row: AnnotationListRow) {
    await setFilters(similarChange(filters.value, row))
  }

  async function resetFilters () {
    // The order of the rows is a display setting, not a filter: it stays.
    filters.value = { ...defaultFilters(), sort: filters.value.sort, descending: filters.value.descending }
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
    if (!value) {
      selection.remove(rows.value.map(r => r.id))
      return true
    }
    return selection.add(rows.value.map(r => [r.id, r.editVersion ?? 0] as const),
      Object.fromEntries(rows.value.map(r => [r.id, r.attributeVersion ?? 0])))
  }

  /**
   * Shows what an assignment of `attributeId` answered (#331): the values and attribute
   * version the server returned replace the listed ones, for saved annotations and for those
   * refused because someone changed them, so a row never keeps its stale copy.
   */
  function applyAssignment (attributeId: string, result: AttributeAssignResult) {
    const versions = result.versions ?? {}
    const values = result.values ?? {}
    const update = (row: AnnotationListRow): AnnotationListRow => {
      if (!(row.id in versions) && !(row.id in values)) return row
      const attributes = { ...(row.attributes ?? {}) }
      const held = values[row.id]
      if (held) {
        if (held.length) attributes[attributeId] = held
        else delete attributes[attributeId]
      }
      return { ...row, attributes, attributeVersion: versions[row.id] ?? row.attributeVersion }
    }
    if (page.value) page.value = { ...page.value, rows: page.value.rows.map(update) }
    const focused = selection.focused
    if (focused) {
      const next = update(focused)
      if (next !== focused) selection.focused = next
    }
  }

  /** Forgets everything (sign-out, another account). */
  function clear () {
    scope.reset()
    reset()
    collectionId.value = null
    selection.clear()
    useAnnotationReviewStore().clear()
    useAttributeAssignStore().clear()
  }

  return {
    collectionId,
    filters,
    offset,
    page,
    rows,
    total,
    needsText,
    loading,
    error,
    documents,
    documentsError,
    shown,
    shownError,
    hiddenSelected,
    resolving,
    people,
    scrollY,
    shownAttributeIds,
    open,
    load,
    readFocused,
    loadDocuments,
    loadShown,
    selectAllMatches,
    deselectHidden,
    setFilters,
    findSimilar,
    resetFilters,
    goTo,
    setPageSelected,
    applyAssignment,
    clear
  }
})
