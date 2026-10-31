import { defineStore } from 'pinia'
import { ref } from 'vue'

import type { Attribute, PatchAttribute, PatchAttributeValue, PostAttribute, PostAttributeValue } from 'src/generated/api'
import { apiErrorMessage, captureSession, createContextGuard, createScope, errorStatus } from 'src/shared/api'
import { useAttributesRepository } from './useAttributesRepository'
import { KIND_LABELS, specialValue, type SpecialKind } from './attributeForm'

/** A refused or failed definition write, with the backend's message (e.g. the number of
 * annotations a narrowing of the tags affects, for a 409). */
export class AttributeWriteError extends Error {
  constructor (message: string, readonly status: number | null) {
    super(message)
    this.name = 'AttributeWriteError'
  }
}

const byName = (a: Attribute, b: Attribute) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })

/**
 * The attribute definitions of one collection (#331, ADR 0011): attributes with their values,
 * retired ones included. The UI retires and restores them and never deletes them (#506); one
 * deleted elsewhere is gone with the next load. Loading another collection first drops the
 * current ones, and an answer for an earlier collection, an earlier reload or an earlier
 * session is ignored.
 *
 * Every write answers with the whole attribute, which replaces the listed one unless the
 * listed one is newer (`revision` counts its edits), so answers arriving out of order never
 * bring back an older state; a list read before a write answered keeps what the write brought
 * (e.g. an attribute created meanwhile). A write that fails throws an `AttributeWriteError` carrying the
 * backend's message; nothing changes locally then.
 */
export const useAttributesStore = defineStore('attributes', () => {
  const repository = useAttributesRepository()
  const scope = createScope()
  const listRequests = createContextGuard()
  const attributes = ref<Attribute[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  // When each attribute was last kept from a write answer (a running count), so a list read
  // before that answer does not drop it.
  let writes = 0
  const keptAt = new Map<string, number>()

  function keep (attribute: Attribute) {
    keptAt.set(attribute.id, ++writes)
    const index = attributes.value.findIndex(a => a.id === attribute.id)
    if (index < 0) {
      attributes.value = [...attributes.value, attribute].sort(byName)
    } else if ((attribute.revision ?? 0) >= (attributes.value[index]!.revision ?? 0)) {
      const next = [...attributes.value]
      next[index] = attribute
      attributes.value = next.sort(byName)
    }
  }

  async function load (collectionId: string) {
    if (scope.enter(collectionId)) {
      attributes.value = []
      keptAt.clear()
    }
    listRequests.enter()
    const isCurrent = listRequests.capture()
    const inSession = captureSession()
    const applies = () => isCurrent() && inSession()
    loading.value = true
    error.value = null
    const sent = writes
    try {
      const list = await repository.getAll(collectionId)
      if (!applies()) return
      // Keep a listed attribute that is newer than the answer, and one a write answered with
      // after the request was sent (created meanwhile, so not in the list).
      const listed = new Map(attributes.value.map(a => [a.id, a]))
      const answered = new Set(list.map(a => a.id))
      const keptMeanwhile = attributes.value.filter(a => !answered.has(a.id) && (keptAt.get(a.id) ?? 0) > sent)
      attributes.value = list
        .map(a => {
          const known = listed.get(a.id)
          return known && (known.revision ?? 0) > (a.revision ?? 0) ? known : a
        })
        .concat(keptMeanwhile)
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

  const addValue = (collectionId: string, attributeId: string, value: PostAttributeValue) =>
    write(collectionId, () => repository.addValue(collectionId, attributeId, value), keep,
      'The value could not be added.')

  const updateValue = (collectionId: string, attributeId: string, valueId: string, patch: PatchAttributeValue) =>
    write(collectionId, () => repository.updateValue(collectionId, attributeId, valueId, patch), keep,
      'The value could not be saved.')

  /** Offers (`allowed`) or withdraws a special kind of the attribute as it is known: withdrawing
   * retires its value, so the assignments it has stay; offering it again restores that value,
   * keeping its id, and adds one only when the attribute never had one (at most one of each
   * kind, retired ones included). Already as asked: no write, the attribute as given. */
  async function setSpecialValue (collectionId: string, attribute: Attribute, kind: SpecialKind,
    allowed: boolean): Promise<Attribute> {
    const existing = specialValue(attribute, kind)
    if (!existing) {
      return allowed ? addValue(collectionId, attribute.id, { label: KIND_LABELS[kind], kind }) : attribute
    }
    if (!existing.retired === allowed) return attribute
    return updateValue(collectionId, attribute.id, existing.id, { retired: !allowed })
  }

  /** Forgets everything (sign-out). */
  function clear () {
    scope.reset()
    listRequests.enter()
    keptAt.clear()
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
    addValue,
    updateValue,
    setSpecialValue,
    clear
  }
})
