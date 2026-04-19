import { computed, ref, reactive } from 'vue'

export interface TagNavItem {
  spanId: string
  chunkId: string
  tagId: string
  start: number
  end: number
}

const items = ref<TagNavItem[]>([])
const currentIndex = ref<Record<string, number>>({})
let scrollCallback: ((item: TagNavItem) => void) | null = null
let highlightCallback: ((spanId: string | null) => void) | null = null

// ── Tag visibility ──
const hiddenTagIds = reactive(new Set<string>())

function isTagVisible(tagId: string): boolean {
  return !hiddenTagIds.has(tagId)
}

function toggleTag(tagId: string) {
  if (hiddenTagIds.has(tagId)) {
    hiddenTagIds.delete(tagId)
  } else {
    hiddenTagIds.add(tagId)
  }
}

function hideAllTags(tagIds: string[]) {
  for (const id of tagIds) hiddenTagIds.add(id)
}

function showAllTags() {
  hiddenTagIds.clear()
}

const groups = computed(() => {
  const map = new Map<string, TagNavItem[]>()
  for (const item of items.value) {
    if (!map.has(item.tagId)) map.set(item.tagId, [])
    map.get(item.tagId)!.push(item)
  }
  return Array.from(map, ([tagId, list]) => ({ tagId, items: list }))
})

function spanCount(tagId: string): number {
  return groups.value.find(g => g.tagId === tagId)?.items.length ?? 0
}

function navIndex(tagId: string): number | null {
  return currentIndex.value[tagId] ?? null
}

function navigate(tagId: string, direction: 'prev' | 'next') {
  const group = groups.value.find(g => g.tagId === tagId)
  if (!group || group.items.length === 0) return

  const cur = currentIndex.value[tagId] ?? -1
  let next: number
  if (direction === 'next') {
    next = cur + 1 >= group.items.length ? 0 : cur + 1
  } else {
    next = cur - 1 < 0 ? group.items.length - 1 : cur - 1
  }

  currentIndex.value[tagId] = next
  const item = group.items[next]
  highlightCallback?.(item.spanId)
  scrollCallback?.(item)
}

function setItems(newItems: TagNavItem[]) {
  items.value = newItems
}

function syncIndex(tagId: string, spanId: string) {
  const group = groups.value.find(g => g.tagId === tagId)
  if (!group) return
  const idx = group.items.findIndex(i => i.spanId === spanId)
  if (idx !== -1) currentIndex.value[tagId] = idx
}

function onScroll(cb: (item: TagNavItem) => void) {
  scrollCallback = cb
}

function onHighlight(cb: (spanId: string | null) => void) {
  highlightCallback = cb
}

export function useTagNavigation() {
  return {
    groups,
    currentIndex,
    hiddenTagIds,
    spanCount,
    navIndex,
    navigate,
    setItems,
    syncIndex,
    onScroll,
    onHighlight,
    isTagVisible,
    toggleTag,
    hideAllTags,
    showAllTags
  }
}
