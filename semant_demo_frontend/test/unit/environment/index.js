// Vitest's jsdom environment, but timers a test file leaves behind end with it (#551).
//
// Vitest 0.23's jsdom `teardown` only removes the jsdom globals (`document`,
// `getComputedStyle`, ...) and keeps the file's worker until the main thread has the file's
// answer. A timer still pending then, such as a Quasar notification removing itself 6 s after
// it was shown or jsdom's `requestAnimationFrame` interval, throws in that worker. When the
// error reaches the pool just before the file's answer, Tinypool reports "Unexpected message
// from Worker" and the whole run fails although every test passed.
//
// This environment clears those timers in its `teardown`, right before the globals go, so
// everything a file runs before then (hooks, cleanups, late promise continuations) is
// covered. Nothing of the file runs after its teardown, so no test result can change.
//
// Vitest 0.23 loads a custom environment only from a package named
// `vitest-environment-<name>`; this directory is linked as `vitest-environment-jsdom-timers`
// (package.json, devDependencies). Select it with `environment: 'jsdom-timers'`.
import { builtinEnvironments } from 'vitest/environments'
import { trackTimers } from './timers.js'

export default {
  name: 'jsdom-timers',
  async setup (global, options) {
    const timers = trackTimers(global)
    const jsdom = await builtinEnvironments.jsdom.setup(global, options)
    return {
      async teardown (global) {
        timers.end()
        await jsdom.teardown(global)
      }
    }
  }
}
