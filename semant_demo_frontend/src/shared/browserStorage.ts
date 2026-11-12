/**
 * localStorage for per-browser preferences (view modes, sizes, widths). Storage can be
 * unavailable or throw (private mode, blocked site data, quota); then nothing is read and a
 * choice just isn't remembered.
 */
export function readStored (key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

/** Whether the value was stored (false when storage is unavailable or full). */
export function writeStored (key: string, value: string): boolean {
  try {
    localStorage.setItem(key, value)
    return true
  } catch {
    // Storage unavailable — the choice just won't persist.
    return false
  }
}

export function removeStored (key: string): void {
  try {
    localStorage.removeItem(key)
  } catch {
    // Storage unavailable — there is nothing to remove.
  }
}

/** The stored keys starting with `prefix`; none when storage is unavailable. */
export function storedKeys (prefix: string): string[] {
  try {
    const keys: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key?.startsWith(prefix)) keys.push(key)
    }
    return keys
  } catch {
    return []
  }
}
