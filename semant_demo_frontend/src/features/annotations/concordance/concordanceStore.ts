import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'
import {
  AnnotationSort, RetrievalMode, SpanType, TextScope, type AnnotatedDocument, type AnnotationFilters, type AnnotationListRow, type AnnotationPage,
  type AnnotationRanking, type AttributeAssignResult, type CollectionPerson, type DocumentFilters, type NearFilter
} from 'src/generated/api'
import { apiErrorMessage, captureSession, createContextGuard, createScope, errorStatus, isAbortError, useApi } from 'src/shared/api'
import { MAX_SELECTION, useAnnotationSelectionStore } from '../annotationSelectionStore'
import { useAttributeAssignStore } from 'src/features/attributes/attributeAssignStore'
import { useAnnotationReviewStore } from './annotationReviewStore'

/** Rows per page of the concordance. */
export const PAGE_SIZE = 50

/** The `k` of a ranked query (#664) is not a toolbar choice (#716): the server default applies, and
 * results always report it as a bounded top-k. */
export const DEFAULT_TOP_K = 100

/** What the concordance shows; every change goes back to the first page. */
export interface ConcordanceFilters {
  tagIds: string[]
  /** `pos` (manual or approved) and `auto` (proposals) by default; `neg` only when chosen. */
  types: SpanType[]
  /** Words that must each occur inside a word of a field of `textScope`, ignoring case (#663): a
   * hard filter, whatever else ranks (#716). */
  text: string
  /** Text to rank by (#716): with it the annotations matching every filter (words included) are
   * ranked by meaning and words (hybrid), as a bounded top-k; never a filter itself. */
  similarity: string
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
  /** Proximity (#333): only annotations with (or, `absent`, without) a neighbor annotation of
   * the chosen tags in the same document, in `relation`; null for no proximity filter. */
  near: NearFilter | null
  /** Lexical mode only; ranked results are in relevance order. */
  sort: AnnotationSort
  /** The attribute whose values order the rows (#666), with `sort` `attribute`; otherwise null. */
  sortAttribute: string | null
  /** Reverses `sort` (missing titles, years and attribute values stay last; rows without a text
   * or context sort key move from first to last). */
  descending: boolean
  /** Derived by `withMode`, never chosen: every match (`lexical`), a ranked top `k` by `similarity`
   * (`hybrid`), or like `similarTo` (`similar`). */
  mode: RetrievalMode
  k: number
  /** Mode `similar`: the source annotation, as listed when it was chosen. */
  similarTo: AnnotationListRow | null
  /** Mode `similar`: rank the source too. */
  includeSource: boolean
}

/** The filter change that drops the Find similar source. */
export function clearSimilar (): Partial<ConcordanceFilters> {
  return { similarTo: null, includeSource: false }
}

/** The filter change of Find similar from `row`, keeping the other filters. It replaces a
 * similarity text (two rankings cannot combine) and never turns that text into a source query. */
export function similarChange (row: AnnotationListRow): Partial<ConcordanceFilters> {
  return { similarTo: row, includeSource: false, similarity: '' }
}

/** `f` with its retrieval mode derived from what is set: a Find similar source, else a similarity
 * text (hybrid), else none (every match). The source and the text exclude each other. */
export function withMode (f: ConcordanceFilters): ConcordanceFilters {
  const mode = f.similarTo ? RetrievalMode.similar : f.similarity.trim() ? RetrievalMode.hybrid : RetrievalMode.lexical
  return { ...f, mode, includeSource: mode === RetrievalMode.similar && f.includeSource }
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
    similarity: '',
    textScope: TextScope.annotation,
    documentIds: [],
    documentFilters: {},
    attributeValues: [],
    attributeUnassigned: [],
    near: null,
    sort: AnnotationSort.document,
    sortAttribute: null,
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

/** The annotation query (`AnnotationFilters`, #663) of the concordance filters, for request bodies. */
export function annotationFilters (f: ConcordanceFilters): AnnotationFilters {
  return {
    tagIds: f.tagIds.length ? f.tagIds : null,
    types: f.types,
    q: f.text.trim() || null,
    rankingQuery: f.mode === RetrievalMode.hybrid ? f.similarity.trim() : null,
    textScope: f.textScope,
    documentIds: f.documentIds.length ? f.documentIds : null,
    documentFilters: normalizeDocumentFilters(f.documentFilters),
    attributeValues: f.attributeValues.length ? f.attributeValues : undefined,
    attributeUnassigned: f.attributeUnassigned.length ? f.attributeUnassigned : undefined,
    near: f.near ?? undefined
  }
}

/** The proximity filter as GET parameters (#333); none without one. */
export function nearParameters (near: NearFilter | null) {
  if (!near) return {}
  return {
    nearRelation: near.relation,
    nearTagId: near.tagIds?.length ? near.tagIds : undefined,
    nearType: near.types?.length ? near.types : undefined,
    nearAttribute: near.attributeValues?.length ? near.attributeValues : undefined,
    nearDistance: near.distance,
    nearUnit: near.unit,
    nearDirection: near.direction,
    nearAbsent: near.absent || undefined
  }
}

/** The request body of the concordance filters for resolving annotation ids. */
function idsRequest (f: ConcordanceFilters, within?: string[]) {
  return { ...annotationFilters(f), within: within ?? null, ranking: ranking(f) }
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
  /** Listed rows that a review made here took out of the filters (#690): they stay where they
   * are, at their new state, until the query is read again (filters, page, sort, Refresh). */
  const unmatched = ref<Set<string>>(new Set())
  /** The query and offset of `page`. */
  let pageKey: string | null = null
  /** Reads of reviewed rows in place; a newer one, or a read of the page, drops their answer. */
  const refreshRequests = createContextGuard()

  const rows = computed(() => page.value?.rows ?? [])
  const total = computed(() => page.value?.total ?? 0)
  /** The offset of the next page: rows of this page that left the result moved the later ones
   * up, so these are not skipped (#690). */
  const nextOffset = computed(() => offset.value + rows.value.length -
    rows.value.filter(r => unmatched.value.has(r.id)).length)
  const hasNextPage = computed(() => offset.value + rows.value.length < total.value)
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
    unmatched.value = new Set()
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

  /** The annotation `annotationId` of the collection as it is now, whatever the filters (e.g. a
   * neighbor that made a row match the proximity filter, #333); null when it no longer exists. */
  async function readRow (annotationId: string): Promise<AnnotationListRow | null> {
    const id = collectionId.value
    if (!id) return null
    const result = await api.listCollectionAnnotationsApiUserCollectionsCollectionIdAnnotationsGet({
      collectionId: id, annotationId: [annotationId], type: Object.values(SpanType), limit: 1
    })
    return result.rows[0] ?? null
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
    refreshRequests.enter()
    const isCurrent = rowRequests.capture()
    const inScope = scope.capture()
    const inSession = captureSession()
    const applies = () => isCurrent() && inScope() && inSession()
    const controller = new AbortController()
    rowAbort = controller
    const f = filters.value
    const key = JSON.stringify([f, offset.value])
    error.value = null
    const ranked = ranking(f)
    loading.value = true
    try {
      const result = await api.listCollectionAnnotationsApiUserCollectionsCollectionIdAnnotationsGet({
        collectionId: id,
        tagId: f.tagIds.length ? f.tagIds : undefined,
        type: f.types,
        q: f.text.trim() || undefined,
        rankingQuery: f.mode === RetrievalMode.hybrid ? f.similarity.trim() : undefined,
        textScope: f.text.trim() ? f.textScope : undefined,
        documentId: f.documentIds.length ? f.documentIds : undefined,
        yearMin: f.documentFilters.yearMin ?? undefined,
        yearMax: f.documentFilters.yearMax ?? undefined,
        titleContains: f.documentFilters.titleContains?.length ? f.documentFilters.titleContains : undefined,
        libraries: f.documentFilters.libraries?.length ? f.documentFilters.libraries : undefined,
        languages: f.documentFilters.languages?.length ? f.documentFilters.languages : undefined,
        attribute: f.attributeValues.length ? f.attributeValues : undefined,
        unassigned: f.attributeUnassigned.length ? f.attributeUnassigned : undefined,
        ...nearParameters(f.near),
        sort: ranked ? undefined : f.sort,
        sortAttribute: !ranked && f.sort === AnnotationSort.attribute ? f.sortAttribute ?? undefined : undefined,
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
      unmatched.value = new Set()
      // Rows on the page match the filters: checking one never makes it hidden.
      noteShown(result.rows.map(r => r.id))
    } catch (e) {
      if (!applies() || isAbortError(e)) return
      page.value = null
      const status = errorStatus(e)
      // A ranked query is refused with a message of its own: no vector of the source (400), no
      // embedding service (503); so is a sort this store cannot give (503: no sort keys or
      // attributes, #666; 404: the sort attribute was deleted).
      const message = ranked && (status === 400 || status === 503)
        ? await apiErrorMessage(e, 'Search by meaning is not available now.')
        : !ranked && (status === 503 || (status === 404 && f.sort === AnnotationSort.attribute))
            ? await apiErrorMessage(e, 'This sort is not available now.')
            : failure(e, 'annotations')
      if (applies()) error.value = message
    } finally {
      if (applies()) {
        loading.value = false
        rowAbort = null
      }
    }
  }

  /**
   * Shows the listed rows among `ids` as they are now, where they are (#690): a review changes
   * the list only when the query is read again. Rows the filters no longer match stay, marked
   * `unmatched`; deleted ones leave the page. The total stays as read. Falls back to reading the
   * page when the rows cannot be read.
   */
  async function refreshRows (ids: Iterable<string>) {
    const id = collectionId.value
    const wanted = new Set(ids)
    const listed = rows.value.filter(r => wanted.has(r.id)).map(r => r.id)
    if (!id || !page.value || !listed.length) return
    refreshRequests.enter()
    const isCurrent = refreshRequests.capture()
    const inScope = scope.capture()
    const inSession = captureSession()
    const key = pageKey
    const applies = () => isCurrent() && inScope() && inSession() && key === pageKey
    try {
      const near = filters.value.near
      const [fresh, matching, nearby] = await Promise.all([
        api.listCollectionAnnotationsApiUserCollectionsCollectionIdAnnotationsGet({
          collectionId: id, annotationId: listed, type: Object.values(SpanType), limit: listed.length
        }),
        api.resolveCollectionAnnotationIdsApiUserCollectionsCollectionIdAnnotationsIdsPost({
          collectionId: id, annotationIdsRequest: idsRequest(filters.value, listed)
        }),
        // The neighbors that explain a row (#333) come only with the proximity filter: read them
        // again for the rows it still matches, as they are now (boundaries may have moved).
        near
          ? api.listCollectionAnnotationsApiUserCollectionsCollectionIdAnnotationsGet({
            collectionId: id, annotationId: listed, type: Object.values(SpanType), limit: listed.length, ...nearParameters(near)
          })
          : Promise.resolve(null)
      ])
      if (!applies() || !page.value) return
      const current = new Map(fresh.rows.map(r => [r.id, r]))
      const matched = new Set(matching.ids)
      const read = new Set(listed)
      const neighbors = new Map((nearby?.rows ?? []).map(r => [r.id, r.neighbors ?? []]))
      // The listed copy keeps what only the page's query gives (e.g. a rank's score); its
      // neighbors are replaced by those read with the proximity filter (none: no longer near).
      const update = (row: AnnotationListRow) => {
        const now = current.get(row.id)
        if (!now) return row
        const merged = { ...row, ...Object.fromEntries(Object.entries(now).filter(([, v]) => v !== undefined)) }
        return { ...merged, neighbors: near ? neighbors.get(row.id) ?? [] : row.neighbors }
      }
      page.value = {
        ...page.value,
        rows: page.value.rows.filter(r => !read.has(r.id) || current.has(r.id)).map(r => read.has(r.id) ? update(r) : r)
      }
      const next = new Set(unmatched.value)
      for (const i of read) {
        if (current.has(i) && !matched.has(i)) next.add(i)
        else next.delete(i)
      }
      unmatched.value = next
      const focused = selection.focused
      if (focused && read.has(focused.id)) {
        const row = page.value.rows.find(r => r.id === focused.id)
        if (row) selection.focus(row)
        else selection.focusedGone = true
      }
    } catch (e) {
      if (!applies()) return
      console.error('Reading the reviewed annotations failed', e)
      await load()
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
    // A new similarity text replaces a Find similar source; the mode follows from what is set.
    filters.value = withMode({ ...before, ...change, ...(change.similarity?.trim() ? clearSimilar() : {}) })
    if (change.documentFilters) filters.value.documentFilters = normalizeDocumentFilters(change.documentFilters)
    if (filters.value.sort !== AnnotationSort.attribute) filters.value.sortAttribute = null
    offset.value = 0
    stopResolving()
    shown.value = new Set()
    known.value = new Set()
    const facetsChanged = 'tagIds' in change || 'types' in change
    await Promise.all([load(), facetsChanged ? loadDocuments() : Promise.resolve(), loadShown()])
  }

  /** Lists the annotations most similar to `row`, within the current filters (#664). */
  async function findSimilar (row: AnnotationListRow) {
    await setFilters(similarChange(row))
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

  async function goTo (to: number) {
    if (to < 0 || (page.value && to >= page.value.total)) return
    offset.value = to
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
    nextOffset,
    hasNextPage,
    unmatched,
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
    refreshRows,
    readFocused,
    readRow,
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
