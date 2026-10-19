const STORAGE_PREFIX = 'semant.lastUsedTag.'

/** The last tag applied to a span in `collectionId`, remembered per-browser (not per-device). */
export function getLastUsedTagId(collectionId: string): string | null {
  try {
    return localStorage.getItem(STORAGE_PREFIX + collectionId)
  } catch {
    return null
  }
}

export function setLastUsedTagId(collectionId: string, tagId: string): void {
  try {
    localStorage.setItem(STORAGE_PREFIX + collectionId, tagId)
  } catch {
    // Storage unavailable (private mode, quota) — the suggestion just won't persist.
  }
}
