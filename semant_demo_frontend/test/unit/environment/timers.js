// Tracks the timeouts and intervals a test file creates, so the test environment can end
// them before it removes the jsdom globals (#551, see `index.js`).
//
// The tracked functions behave like Node's: the same own properties (such as
// `util.promisify.custom`), the same validation of the handler (it is passed through
// unchanged when it is not a function), the `Timeout` as `this` in the callback, and the
// same handles. Vitest's own timers are copies it saved before any file ran.

const names = ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval']
const noop = () => undefined

/**
 * Replaces the timer functions of `global` with tracked ones.
 *
 * `end()` clears every timer and interval still pending, makes callbacks that would still
 * run return at once, and puts the original functions back. Timers created afterwards
 * through a tracked function that someone kept are not scheduled at all.
 *
 * @param {typeof globalThis} global
 * @returns {{ pending: () => number, end: () => void }}
 */
export function trackTimers (global) {
  /** @type {Record<string, any>} */
  const real = Object.fromEntries(names.map((name) => [name, global[name]]))
  const pending = new Set()
  let ended = false

  /**
   * @param {Function} schedule
   * @param {boolean} repeats
   */
  function track (schedule, repeats) {
    /** @this {unknown} */
    function tracked (/** @type {unknown} */ handler, /** @type {unknown[]} */ ...rest) {
      if (typeof handler !== 'function') return schedule.call(this, handler, ...rest)
      if (ended) {
        const handle = schedule.call(this, noop, ...rest.slice(0, 1))
        real.clearTimeout(handle)
        return handle
      }
      const handle = schedule.call(this, function (/** @type {unknown[]} */ ...args) {
        if (!repeats) pending.delete(handle)
        if (ended) return undefined
        return handler.apply(this, args)
      }, ...rest)
      pending.add(handle)
      // A `Timeout` refreshed after it fired runs again with the same handle.
      if (handle && typeof handle.refresh === 'function') {
        const refresh = handle.refresh
        handle.refresh = function () {
          if (!ended) pending.add(handle)
          return refresh.call(this)
        }
      }
      return handle
    }
    Object.defineProperties(tracked, Object.getOwnPropertyDescriptors(schedule))
    return tracked
  }

  /** @param {Function} clear */
  function untrack (clear) {
    /** @this {unknown} */
    function tracked (/** @type {unknown} */ handle) {
      pending.delete(handle)
      return clear.call(this, handle)
    }
    Object.defineProperties(tracked, Object.getOwnPropertyDescriptors(clear))
    return tracked
  }

  const replacements = {
    setTimeout: track(real.setTimeout, false),
    clearTimeout: untrack(real.clearTimeout),
    setInterval: track(real.setInterval, true),
    clearInterval: untrack(real.clearInterval)
  }
  Object.assign(global, replacements)

  return {
    pending: () => pending.size,
    end () {
      ended = true
      // Node clears timeouts and intervals with either function.
      for (const handle of pending) real.clearTimeout(handle)
      pending.clear()
      Object.assign(global, real)
    }
  }
}
