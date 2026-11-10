import { afterAll } from 'vitest'

// jsdom does not lay out pages, and its window.scrollTo only reports "Not implemented" with a
// stack trace (Quasar calls it when a dialog locks the page scroll). Nothing here scrolls.
// Specs in the node environment (devTooling) have no window.
if (typeof window !== 'undefined') window.scrollTo = () => undefined

// Timers a spec file leaves behind are cleared when the file ends (#551). Vitest 0.23 removes
// the jsdom globals (`document`, `getComputedStyle`, ...) after a file but keeps its worker
// until the main thread has its answer; a timer still pending, such as a Quasar notification
// removing itself 6 s after it was shown, then throws in that worker. When the error reaches
// the pool just before the file's answer, Tinypool reports "Unexpected message from Worker"
// and the whole run fails although every test passed. A timer pending after a file's last
// test cannot change any of its results. Vitest's own timers are separate copies.

// Handles are Node's `Timeout` objects here, numbers in the DOM types: kept opaque.
const pending = new Set<unknown>()
const { setTimeout: realSetTimeout, clearTimeout: realClearTimeout } = globalThis
const clear = (id: unknown) => realClearTimeout(id as Parameters<typeof clearTimeout>[0])

globalThis.setTimeout = ((handler: TimerHandler, timeout?: number, ...args: unknown[]) => {
  const id: unknown = realSetTimeout((...callArgs: unknown[]) => {
    pending.delete(id)
    if (typeof handler === 'function') handler(...callArgs)
  }, timeout, ...args)
  pending.add(id)
  return id
}) as typeof setTimeout

globalThis.clearTimeout = ((id?: unknown) => {
  pending.delete(id)
  clear(id)
}) as typeof clearTimeout

afterAll(() => {
  for (const id of pending) clear(id)
  pending.clear()
})
