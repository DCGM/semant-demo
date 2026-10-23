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

export function writeStored (key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Storage unavailable — the choice just won't persist.
  }
}
