import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'
import type { AnnotationListRow } from 'src/generated/api'
import { createScope } from 'src/shared/api'

/** Annotations one selection may hold; the backend resolves at most this many matches. */
export const MAX_SELECTION = 5000

/**
 * The annotations a researcher chose in one collection's workspace (#459): the checked
 * annotations as explicit ids and the focused occurrence (the one whose source is open).
 * The concordance writes it; statistics and cluster views read the same ids. Nothing here
 * is a query: an empty selection is empty, "all matches" is added as the ids the server
 * resolved at that moment, and changing filters or pages never adds or removes members.
 *
 * Entering another collection starts afresh; signing out or another account clears it
 * (`app/session.ts`). Writers use `captureScope` to drop answers of a collection left meanwhile and
 * `captureMembership` to stop a review of the members once they changed.
 */
export const useAnnotationSelectionStore = defineStore('annotationSelection', () => {
  const scope = createScope()
  const collectionId = ref<string | null>(null)
  const ids = ref<Set<string>>(new Set())
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

  /** Adds the ids unless the selection would exceed `MAX_SELECTION`; false then, and nothing changes. */
  function add (list: Iterable<string>): boolean {
    const next = new Set(ids.value)
    for (const id of list) next.add(id)
    if (next.size > MAX_SELECTION) return false
    setIds(next)
    return true
  }

  function remove (list: Iterable<string>) {
    const next = new Set(ids.value)
    for (const id of list) next.delete(id)
    setIds(next)
  }

  function toggle (id: string, value?: boolean): boolean {
    if (value ?? !ids.value.has(id)) return add([id])
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
