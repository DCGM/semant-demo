import { defineStore } from 'pinia'
import { ref } from 'vue'

import type { Attribute, PatchAttribute, PatchAttributeValue, PostAttribute, PostAttributeValue } from 'src/generated/api'
import { apiErrorMessage, captureSession, createContextGuard, createScope, errorStatus } from 'src/shared/api'
import { useAttributesRepository } from './useAttributesRepository'

/** A refused or failed definition write, with the backend's message (e.g. the number of
 * annotations that hold a value, for a 409). */
export class AttributeWriteError extends Error {
  constructor (message: string, readonly status: number | null) {
    super(message)
    this.name = 'AttributeWriteError'
  }
}

const byName = (a: Attribute, b: Attribute) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })

/**
 * The attribute definitions of one collection (#331, ADR 0011): attributes with their values,
 * retired ones included. Loading another collection first drops the current ones, and an
 * answer for an earlier collection, an earlier reload or an earlier session is ignored.
 *
 * Every write answers with the whole attribute, which replaces the listed one unless the
 * listed one is newer (`revision` counts its edits), so answers arriving out of order never
 * bring back an older state. A write that fails throws an `AttributeWriteError` carrying the
 * backend's message; nothing changes locally then.
 */
export const useAttributesStore = defineStore('attributes', () => {
  const repository = useAttributesRepository()
  const scope = createScope()
  const listRequests = createContextGuard()
  const attributes = ref<Attribute[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  // Attributes deleted in this scope; ids are never reused, so an older list cannot bring one back.
  const deletedIds = new Set<string>()

  function keep (attribute: Attribute) {
    if (deletedIds.has(attribute.id)) return
    const index = attributes.value.findIndex(a => a.id === attribute.id)
    if (index < 0) {
      attributes.value = [...attributes.value, attribute].sort(byName)
    } else if ((attribute.revision ?? 0) >= (attributes.value[index]!.revision ?? 0)) {
      const next = [...attributes.value]
      next[index] = attribute
      attributes.value = next.sort(byName)
    }
  }

  function forget (attributeId: string) {
    deletedIds.add(attributeId)
    attributes.value = attributes.value.filter(a => a.id !== attributeId)
  }

  async function load (collectionId: string) {
    if (scope.enter(collectionId)) {
      attributes.value = []
      deletedIds.clear()
    }
    listRequests.enter()
    const isCurrent = listRequests.capture()
    const inSession = captureSession()
    const applies = () => isCurrent() && inSession()
    loading.value = true
    error.value = null
    try {
      const list = await repository.getAll(collectionId)
      if (!applies()) return
      // Keep a listed attribute that is newer than the answer (a write answered meanwhile).
      const listed = new Map(attributes.value.map(a => [a.id, a]))
      attributes.value = list
        .filter(a => !deletedIds.has(a.id))
        .map(a => {
          const known = listed.get(a.id)
          return known && (known.revision ?? 0) > (a.revision ?? 0) ? known : a
        })
        .sort(byName)
    } catch (e) {
      if (applies()) error.value = await apiErrorMessage(e, 'The attributes could not be loaded.')
    } finally {
      if (applies()) loading.value = false
    }
  }

  /** Runs a write of `collectionId`; `apply` takes its answer while the collection and the
   * session are still the current ones. */
  async function write<T> (collectionId: string, request: () => Promise<T>, apply: (result: T) => void,
    fallback: string): Promise<T> {
    const inScope = scope.capture()
    const inSession = captureSession()
    try {
      const result = await request()
      if (inScope() && inSession() && scope.key === collectionId) apply(result)
      return result
    } catch (e) {
      throw new AttributeWriteError(await apiErrorMessage(e, fallback), errorStatus(e))
    }
  }

  const createAttribute = (collectionId: string, attribute: PostAttribute) =>
    write(collectionId, () => repository.create(collectionId, attribute), keep,
      'The attribute could not be created.')

  const updateAttribute = (collectionId: string, attributeId: string, patch: PatchAttribute) =>
    write(collectionId, () => repository.update(collectionId, attributeId, patch), keep,
      'The attribute could not be saved.')

  const deleteAttribute = (collectionId: string, attributeId: string) =>
    write(collectionId, () => repository.delete(collectionId, attributeId), () => forget(attributeId),
      'The attribute could not be deleted.')

  const addValue = (collectionId: string, attributeId: string, value: PostAttributeValue) =>
    write(collectionId, () => repository.addValue(collectionId, attributeId, value), keep,
      'The value could not be added.')

  const updateValue = (collectionId: string, attributeId: string, valueId: string, patch: PatchAttributeValue) =>
    write(collectionId, () => repository.updateValue(collectionId, attributeId, valueId, patch), keep,
      'The value could not be saved.')

  const deleteValue = (collectionId: string, attributeId: string, valueId: string) =>
    write(collectionId, () => repository.deleteValue(collectionId, attributeId, valueId), keep,
      'The value could not be deleted.')

  /** Forgets everything (sign-out). */
  function clear () {
    scope.reset()
    listRequests.enter()
    deletedIds.clear()
    attributes.value = []
    loading.value = false
    error.value = null
  }

  return {
    attributes,
    loading,
    error,
    load,
    createAttribute,
    updateAttribute,
    deleteAttribute,
    addValue,
    updateValue,
    deleteValue,
    clear
  }
})
