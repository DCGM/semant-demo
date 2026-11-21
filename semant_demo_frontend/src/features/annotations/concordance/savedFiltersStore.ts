import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'
import type { SavedSelection } from 'src/generated/api'
import { apiErrorMessage, captureSession, createContextGuard, createScope, useApi } from 'src/shared/api'
import { defaultFilters, useConcordanceStore } from './concordanceStore'
import { filtersOf, liveQueryOf, sameQuery } from './savedFilters'

const byName = (a: SavedSelection, b: SavedSelection) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })

/**
 * The saved live filters of the open collection's annotation workspace (#824). They live on the
 * server, belong to the collection and are shared with its members; the current, unsaved filters
 * stay in the workspace (`concordanceStore`) for this session only. `activeId` is the live filter
 * the workspace was last opened from or saved as; `modified` says whether the filters changed
 * since. Opening a live filter evaluates its query again, so it lists the annotations as they are now.
 *
 * Writes throw an `Error` with the backend's message and change nothing locally when refused.
 * Another collection or a sign-out drops the list and late answers.
 */
export const useSavedFiltersStore = defineStore('savedFilters', () => {
  const api = useApi().default
  const scope = createScope()
  const listRequests = createContextGuard()
  const concordance = useConcordanceStore()

  const collectionId = ref<string | null>(null)
  const items = shallowRef<SavedSelection[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const activeId = ref<string | null>(null)

  const active = computed(() => items.value.find(s => s.id === activeId.value) ?? null)
  const current = computed(() => liveQueryOf(concordance.filters, concordance.shownAttributeIds))
  /** The workspace no longer shows the active live filter as saved. */
  const modified = computed(() => !!active.value?.query && !sameQuery(current.value, active.value.query))

  function keep (selection: SavedSelection) {
    items.value = [...items.value.filter(s => s.id !== selection.id), selection].sort(byName)
  }

  async function load (id: string) {
    if (scope.enter(id)) {
      collectionId.value = id
      items.value = []
      activeId.value = null
    }
    listRequests.enter()
    const isCurrent = listRequests.capture()
    const inScope = scope.capture()
    const inSession = captureSession()
    const applies = () => isCurrent() && inScope() && inSession()
    loading.value = true
    error.value = null
    try {
      const list = await api.listSavedSelectionsApiUserCollectionsCollectionIdSavedSelectionsGet({ collectionId: id })
      if (!applies()) return
      items.value = [...list].sort(byName)
      if (activeId.value && !list.some(s => s.id === activeId.value)) activeId.value = null
    } catch (e) {
      if (applies()) error.value = await apiErrorMessage(e, 'Failed to load the saved filters.')
    } finally {
      if (applies()) loading.value = false
    }
  }

  /** Runs a write for the current collection; its answer is dropped after a switch or sign-out. */
  async function write<T> (run: (id: string) => Promise<T>, failure: string): Promise<T | null> {
    const id = collectionId.value
    if (!id) return null
    const inScope = scope.capture()
    const inSession = captureSession()
    try {
      const result = await run(id)
      return inScope() && inSession() ? result : null
    } catch (e) {
      throw new Error(await apiErrorMessage(e, failure))
    }
  }

  /** Saves the current filters as a new live filter, which becomes the active one. */
  async function saveAs (name: string) {
    const created = await write(collectionId => api.createSavedSelectionApiUserCollectionsCollectionIdSavedSelectionsPost({
      collectionId, postSavedSelection: { name, query: current.value }
    }), 'The filters could not be saved.')
    if (!created) return
    keep(created)
    activeId.value = created.id
  }

  /** Replaces the live filter's query with the current filters. */
  async function update (id: string) {
    const updated = await write(collectionId => api.updateSavedSelectionApiUserCollectionsCollectionIdSavedSelectionsSelectionIdPatch({
      collectionId, selectionId: id, patchSavedSelection: { query: current.value }
    }), 'The saved filter could not be updated.')
    if (!updated) return
    keep(updated)
    activeId.value = updated.id
  }

  async function rename (id: string, name: string) {
    const updated = await write(collectionId => api.updateSavedSelectionApiUserCollectionsCollectionIdSavedSelectionsSelectionIdPatch({
      collectionId, selectionId: id, patchSavedSelection: { name }
    }), 'The saved filter could not be renamed.')
    if (updated) keep(updated)
  }

  async function remove (id: string) {
    const done = await write(collectionId => api.deleteSavedSelectionApiUserCollectionsCollectionIdSavedSelectionsSelectionIdDelete({
      collectionId, selectionId: id
    }).then(() => true), 'The saved filter could not be deleted.')
    if (!done) return
    items.value = items.value.filter(s => s.id !== id)
    if (activeId.value === id) activeId.value = null
  }

  /** Shows the live filter in the workspace: its query evaluated now, its order and columns. */
  async function open (selection: SavedSelection) {
    if (!selection.query) return
    activeId.value = selection.id
    concordance.shownAttributeIds = [...(selection.query.shownAttributeIds ?? [])]
    await concordance.setFilters(filtersOf(selection.query))
  }

  /** Closes the open saved filter: the workspace returns to the default filters and columns. */
  async function close () {
    activeId.value = null
    concordance.shownAttributeIds = []
    await concordance.setFilters(defaultFilters())
  }

  function clear () {
    scope.reset()
    listRequests.enter()
    collectionId.value = null
    items.value = []
    loading.value = false
    error.value = null
    activeId.value = null
  }

  return { collectionId, items, loading, error, activeId, active, modified, load, saveAs, update, rename, remove, open, close, clear }
})
