import { computed, ref, shallowRef, watch, type Ref } from 'vue'
import {
  clearHistory,
  matchingEntries,
  readHistory,
  savedQuery,
  updateHistory,
  withEntry,
  withoutEntry,
  type HistoryAudience,
  type HistoryCriteria,
  type HistoryEntry,
  type StoredHistory
} from './history'

/**
 * The recent searches of one search input and the state of its dropdown (#558).
 *
 * `audience` is whose history is used; null while that is not known (a stored session not
 * verified yet), when nothing is shown or recorded. Changes read the stored list again
 * before writing, so a search made in another tab meanwhile is kept.
 *
 * The stored list is read when the list opens (and when the audience changes), not on
 * every keystroke: typing only narrows what was read.
 *
 * A history written by a newer version of the application (`newerFormat`) is not shown and
 * nothing is recorded into it; the list then asks the user to reload the page, or to clear
 * the history when reloading does not help.
 *
 * Keyboard (`onKeydown` on the input): ArrowDown/ArrowUp open the list and move the
 * highlight, Enter on a highlighted entry picks it (the caller's own Enter handling runs
 * otherwise), Escape closes the list, Shift+Delete removes the highlighted entry. Keys are
 * left to the input when no entry is listed.
 */
export function useSearchHistory<C> (
  criteria: HistoryCriteria<C>,
  audience: Ref<HistoryAudience | null>,
  text: Ref<string>,
  pick: (entry: HistoryEntry<C>) => void
) {
  const entries = shallowRef<HistoryEntry<C>[]>([])
  const newerFormat = ref(false)
  const open = ref(false)
  const activeIndex = ref(-1)

  function apply (history: StoredHistory<C>) {
    entries.value = history.entries
    newerFormat.value = history.newerFormat
  }

  function reload () {
    apply(audience.value ? readHistory(audience.value, criteria) : { entries: [], newerFormat: false })
  }
  // Another audience replaces the whole list (never mixed); an open list stays open, so one
  // opened while the stored session was being verified shows that user's history once it is.
  watch(audience, () => {
    reload()
    activeIndex.value = -1
  }, { immediate: true, deep: true })

  const suggestions = computed(() => matchingEntries(entries.value, text.value))
  const shown = computed(() => open.value && (suggestions.value.length > 0 || newerFormat.value))

  watch(suggestions, (list) => {
    if (activeIndex.value >= list.length) activeIndex.value = list.length - 1
  })
  // Typing changes what is listed; the highlight starts over.
  watch(text, () => { activeIndex.value = -1 })

  /** Opens the list, reading the stored history when it was closed. */
  function show () {
    if (open.value) return
    reload()
    open.value = true
  }

  function close () {
    open.value = false
    activeIndex.value = -1
  }

  /** Changes the stored history; false when it is of a newer format and was left unchanged. */
  function update (change: (current: HistoryEntry<C>[]) => HistoryEntry<C>[]): boolean {
    const target = audience.value
    if (!target) return false
    const history = updateHistory(target, criteria, change)
    apply(history)
    return !history.newerFormat
  }

  /**
   * Adds a search that ran as the newest entry. `tooLong`: the query is longer than
   * MAX_QUERY_LENGTH and not saved (the caller tells the user); `skipped`: a blank query, no
   * known audience or a history of a newer format (the list asks for a reload).
   */
  function record (query: string, searchCriteria: C): 'saved' | 'tooLong' | 'skipped' {
    const saved = savedQuery(query)
    if (saved === null) return query.trim() ? 'tooLong' : 'skipped'
    const done = update(current => withEntry(current, { query: saved, criteria: searchCriteria, savedAt: Date.now() }, criteria))
    return done ? 'saved' : 'skipped'
  }

  function remove (entry: HistoryEntry<C>) {
    update(current => withoutEntry(current, entry, criteria))
  }

  /** Removes the whole history, also one of a newer format. */
  function clear () {
    if (audience.value) clearHistory(audience.value, criteria.namespace)
    apply({ entries: [], newerFormat: false })
    close()
  }

  function choose (entry: HistoryEntry<C>) {
    close()
    pick(entry)
  }

  function move (step: number) {
    const opening = !open.value
    show()
    const count = suggestions.value.length // after a closed list was read again
    if (!count) return
    if (opening) {
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
      move(event.key === 'ArrowDown' ? 1 : -1)
      if (!shown.value || !suggestions.value.length) return false // nothing listed: the caret moves as usual
      event.preventDefault()
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

  return { entries, newerFormat, suggestions, open, shown, activeIndex, show, close, record, remove, clear, choose, onKeydown }
}
