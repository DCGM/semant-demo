import { computed, type Ref } from 'vue'
import type { Tag } from 'src/generated/api'

/**
 * Whether a tag's name or shorthand contains `term` (already trimmed and lower-cased); the
 * tags panel and the popover's tag picker search alike (#770).
 */
export const tagMatches = (tag: Tag, term: string): boolean =>
  tag.name.toLowerCase().includes(term) || !!tag.shorthand?.toLowerCase().includes(term)

export function useTagSearch(sortedTags: Ref<Tag[]>, searchedTagName: Ref<string>) {
  // A ".*term.*" match is just "contains" — using RegExp here would mean
  // interpolating raw user input into `new RegExp(...)`, which throws on
  // unescaped metacharacters (e.g. a tag literally named "C++" or "3.2").
  // `includes()` gives the same contains-semantics with no escaping needed.
  const filteredTags = computed(() => {
    const term = searchedTagName.value.trim().toLowerCase()
    if (!term) return sortedTags.value
    return sortedTags.value.filter((tag) => tagMatches(tag, term))
  })

  return { filteredTags }
}

export default useTagSearch
