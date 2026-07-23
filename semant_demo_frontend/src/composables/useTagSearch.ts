import { computed, type Ref } from 'vue'
import type { Tag } from 'src/models/tags'

export function useTagSearch(sortedTags: Ref<Tag[]>, searchedTagName: Ref<string>) {
  // A ".*term.*" match is just "contains" — using RegExp here would mean
  // interpolating raw user input into `new RegExp(...)`, which throws on
  // unescaped metacharacters (e.g. a tag literally named "C++" or "3.2").
  // `includes()` gives the same contains-semantics with no escaping needed.
  const filteredTags = computed(() => {
    const term = searchedTagName.value.trim().toLowerCase()
    if (!term) return sortedTags.value
    return sortedTags.value.filter((tag) => tag.name.toLowerCase().includes(term))
  })

  return { filteredTags }
}

export default useTagSearch
