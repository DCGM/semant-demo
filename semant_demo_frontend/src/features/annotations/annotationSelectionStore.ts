import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'
import type { AnnotationListRow } from 'src/generated/api'
import { createScope } from 'src/shared/api'

/** Annotations one selection may hold; the backend resolves at most this many matches. */
export const MAX_SELECTION = 5000

/** A selected annotation and the `editVersion` it had when it was added (#460). */
export type SelectionEntry = readonly [id: string, version: number]

/**
 * The annotations a researcher chose in one collection's workspace (#459): the checked
 * annotations as explicit ids and the focused occurrence (the one whose source is open).
 * The concordance writes it; statistics and cluster views read the same ids. Nothing here
 * is a query: an empty selection is empty, "all matches" is added as the ids the server
 * resolved at that moment, and changing filters or pages never adds or removes members.
 *
 * Each member keeps the `editVersion` it had when it was added (#460); a review sends it, so
 * an annotation someone else changed since it was selected is refused, not overwritten. Only
 * this user's own saved writes move it on (`noteVersions`); "Show changed" selects the
 * refused ones again at their current versions (`replace`). Each member also keeps its
 * `attributeVersion` (#331, ADR 0011), which an attribute assignment sends; it is independent of
 * `editVersion` and likewise moved on only by this user's saved assignments
 * (`noteAttributeVersions`).
 *
 * Entering another collection starts afresh; signing out or another account clears it
 * (`app/session.ts`). Writers use `captureScope` to drop answers of a collection left meanwhile and
 * `captureMembership` to stop a review of the members once they changed.
 */
export const useAnnotationSelectionStore = defineStore('annotationSelection', () => {
  const scope = createScope()
  const collectionId = ref<string | null>(null)
  const ids = ref<Set<string>>(new Set())
  /** The version each member had when it was added, moved on by this user's saved writes. */
  let versions = new Map<string, number>()
  /** The `attributeVersion` of each member, likewise. */
  let attributeVersions = new Map<string, number>()
  /** Changes with every change of the members, so a review of them can stop (`captureMembership`). */
  let revision = 0
  /** The row whose source context is open, as the latest page that lists it shows it. */
  const focused = shallowRef<AnnotationListRow | null>(null)
  /** The focused row left its page when the page was read again: it was deleted, or an
   * edit took it out of the filters or moved it to another page; `focused` is outdated. */
  const focusedGone = ref(false)

  const size = computed(() => ids.value.size)

  function setIds (next: Set<string>) {
    ids.value = next
    versions = new Map([...versions].filter(([id]) => next.has(id)))
    attributeVersions = new Map([...attributeVersions].filter(([id]) => next.has(id)))
    revision++
  }

  function reset () {
    setIds(new Set())
    focused.value = null
    focusedGone.value = false
  }

  /** Uses the selection of `id`, forgetting that of another collection. */
  function enter (id: string) {
    if (scope.enter(id)) {
      reset()
      collectionId.value = id
    }
  }

  /** Adds the annotations unless the selection would exceed `MAX_SELECTION`; false then, and
   * nothing changes. A member already selected keeps the versions it was selected at.
   * `attributes`: the `attributeVersion` of the added annotations. */
  function add (entries: Iterable<SelectionEntry>, attributes: Record<string, number> = {}): boolean {
    const next = new Set(ids.value)
    const added: SelectionEntry[] = []
    for (const [id, version] of entries) {
      if (!next.has(id)) added.push([id, version])
      next.add(id)
    }
    if (next.size > MAX_SELECTION) return false
    for (const [id, version] of added) {
      versions.set(id, version)
      attributeVersions.set(id, attributes[id] ?? 0)
    }
    setIds(next)
    return true
  }

  /** Selects exactly these annotations at these versions; `attributes` gives their
   * `attributeVersion`, otherwise a member keeps the one it had. */
  function replace (entries: Iterable<SelectionEntry>, attributes: Record<string, number> = {}) {
    versions = new Map(entries)
    attributeVersions = new Map([...versions.keys()].map(id => [id, attributes[id] ?? attributeVersions.get(id) ?? 0]))
    setIds(new Set(versions.keys()))
  }

  /** The version a review of `id` expects. */
  function versionOf (id: string): number {
    return versions.get(id) ?? 0
  }

  /** The `attributeVersion` an assignment to `id` expects. */
  function attributeVersionOf (id: string): number {
    return attributeVersions.get(id) ?? 0
  }

  /** This user's assignments saved these attribute versions; members keep them. */
  function noteAttributeVersions (saved: Record<string, number>) {
    for (const [id, version] of Object.entries(saved)) {
      if (attributeVersions.has(id)) attributeVersions.set(id, version)
    }
  }

  /** This user's writes saved these versions; members keep them (not a change of the members). */
  function noteVersions (saved: Record<string, number>) {
    for (const [id, version] of Object.entries(saved)) {
      if (versions.has(id)) versions.set(id, version)
    }
  }

  function remove (list: Iterable<string>) {
    const next = new Set(ids.value)
    for (const id of list) next.delete(id)
    setIds(next)
  }

  function toggle (id: string, version: number, value?: boolean, attributeVersion = 0): boolean {
    if (value ?? !ids.value.has(id)) return add([[id, version]], { [id]: attributeVersion })
    remove([id])
    return true
  }

  /** Keeps only the selected ids that are also in `list`. */
  function retain (list: Set<string>) {
    setIds(new Set([...ids.value].filter(id => list.has(id))))
  }

  function clearSelection () {
    setIds(new Set())
  }

  function focus (row: AnnotationListRow | null) {
    focused.value = row
    focusedGone.value = false
  }

  /** True while the selection still belongs to the collection it had when called. */
  function captureScope (): () => boolean {
    return scope.capture()
  }

  /** True while the members are those they were when called (and the collection the same). */
  function captureMembership (): () => boolean {
    const inScope = scope.capture()
    const at = revision
    return () => inScope() && at === revision
  }

  /** Forgets everything (sign-out, another account). */
  function clear () {
    scope.reset()
    reset()
    collectionId.value = null
  }

  return {
    collectionId,
    ids,
    size,
    focused,
    focusedGone,
    enter,
    add,
    replace,
    versionOf,
    noteVersions,
    attributeVersionOf,
    noteAttributeVersions,
    remove,
    toggle,
    retain,
    clearSelection,
    focus,
    captureScope,
    captureMembership,
    clear
  }
})
