import { computed, ref, shallowRef, watch, type Ref } from 'vue'
import {
  matchingEntries,
  normalizeQuery,
  readHistory,
  withEntry,
  withoutEntry,
  writeHistory,
  type HistoryAudience,
  type HistoryCriteria,
  type HistoryEntry
} from './history'

/**
 * The recent searches of one search input and the state of its dropdown (#558).
 *
 * `audience` is whose history is used; null while that is not known (a stored session not
 * verified yet), when nothing is shown or recorded. Changes read the stored list again
 * before writing, so a search made in another tab meanwhile is kept.
 *
 * Keyboard (`onKeydown` on the input): ArrowDown/ArrowUp open the list and move the
 * highlight, Enter on a highlighted entry picks it (the caller's own Enter handling runs
 * otherwise), Escape closes the list, Shift+Delete removes the highlighted entry.
 */
export function useSearchHistory<C> (
  criteria: HistoryCriteria<C>,
  audience: Ref<HistoryAudience | null>,
  text: Ref<string>,
  pick: (entry: HistoryEntry<C>) => void
) {
  const entries = shallowRef<HistoryEntry<C>[]>([])
  const open = ref(false)
  const activeIndex = ref(-1)

  function reload () {
    entries.value = audience.value ? readHistory(audience.value, criteria) : []
  }
  // Another audience replaces the whole list (never mixed); an open list stays open, so one
  // opened while the stored session was being verified shows that user's history once it is.
  watch(audience, () => {
    reload()
    activeIndex.value = -1
  }, { immediate: true, deep: true })

  const suggestions = computed(() => matchingEntries(entries.value, text.value))
  const shown = computed(() => open.value && suggestions.value.length > 0)

  watch(suggestions, (list) => {
    if (activeIndex.value >= list.length) activeIndex.value = list.length - 1
  })
  // Typing changes what is listed; the highlight starts over.
  watch(text, () => { activeIndex.value = -1 })

  function show () {
    reload()
    open.value = true
  }

  function close () {
    open.value = false
    activeIndex.value = -1
  }

  function update (change: (current: HistoryEntry<C>[]) => HistoryEntry<C>[]) {
    const target = audience.value
    if (!target) return
    const next = change(readHistory(target, criteria))
    writeHistory(target, criteria, next)
    entries.value = next
  }

  /** Adds a submitted search as the newest entry; a blank query is not recorded. */
  function record (query: string, searchCriteria: C) {
    const normalized = normalizeQuery(query)
    if (!normalized) return
    update(current => withEntry(current, { query: normalized, criteria: searchCriteria, savedAt: Date.now() }, criteria))
  }

  function remove (entry: HistoryEntry<C>) {
    update(current => withoutEntry(current, entry, criteria))
  }

  function clear () {
    update(() => [])
    close()
  }

  function choose (entry: HistoryEntry<C>) {
    close()
    pick(entry)
  }

  function move (step: number) {
    const count = suggestions.value.length
    if (!count) return
    if (!open.value) {
      show()
      activeIndex.value = step > 0 ? 0 : count - 1
      return
    }
    const next = activeIndex.value + step
    activeIndex.value = next < -1 ? count - 1 : next >= count ? -1 : next
  }

  /** Handles a key on the input; true when the key was used by the history. */
  function onKeydown (event: KeyboardEvent): boolean {
    if (event.isComposing) return false
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (!suggestions.value.length && !open.value) return false
      event.preventDefault()
      move(event.key === 'ArrowDown' ? 1 : -1)
      return true
    }
    if (!shown.value) return false
    const active = suggestions.value[activeIndex.value]
    if (event.key === 'Escape') {
      event.preventDefault()
      close()
      return true
    }
    if (event.key === 'Enter' && active) {
      event.preventDefault()
      choose(active)
      return true
    }
    if (event.key === 'Delete' && event.shiftKey && active) {
      event.preventDefault()
      remove(active)
      return true
    }
    return false
  }

  return { entries, suggestions, open, shown, activeIndex, show, close, record, remove, clear, choose, onKeydown }
}
