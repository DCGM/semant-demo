import { createContextGuard } from './context'

/**
 * State that belongs to one key (a collection, a collection+document...). `enter(key)`
 * switches to a key and reports whether it changed, so the caller can clear the old
 * key's data; `capture()` gives a check that turns false once another key is entered
 * (or `reset()` is called). Requests started for the old key then leave the state alone.
 */
export function createScope () {
  const guard = createContextGuard()
  let current: string | null = null
  return {
    get key (): string | null {
      return current
    },
    /** Switches to `key`; returns true when it differs from the current key. */
    enter (key: string): boolean {
      if (key === current) return false
      current = key
      guard.enter()
      return true
    },
    capture: guard.capture,
    /** Forgets the key (logout, leaving the view): everything captured becomes stale. */
    reset () {
      current = null
      guard.enter()
    }
  }
}

export type Scope = ReturnType<typeof createScope>
