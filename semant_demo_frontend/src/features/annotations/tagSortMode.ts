const STORAGE_KEY = 'semant.tagPanelSort'

/** How the document view's tags panel orders the tags: `custom` is a dragged order. */
export type TagSortMode = 'name' | 'count' | 'custom'

/** The sort mode last chosen in the tags panel, remembered per browser; by count until one is chosen. */
export function getTagSortMode(): Exclude<TagSortMode, 'custom'> {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'name' ? 'name' : 'count'
  } catch {
    return 'count'
  }
}

export function setTagSortMode(mode: Exclude<TagSortMode, 'custom'>): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode)
  } catch {
    // Storage unavailable (private mode, quota) — the choice just won't persist.
  }
}
