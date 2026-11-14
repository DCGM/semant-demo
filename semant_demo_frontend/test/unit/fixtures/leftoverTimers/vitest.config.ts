import { defineConfig, type UserConfig } from 'vitest/config'
import projectConfig from '../../../../vitest.config'

const base = projectConfig as UserConfig

// Runs the two fixture files of `leftoverTimers.spec.ts` (#551) with the unit tests' environment
// and setup, in shared workers (no isolation), so a worker outlives its file as it can in CI.
// Two threads on any machine: with one, both files would share a worker and the second
// file's new jsdom would hide the first file's leftover timers.
export default defineConfig({
  ...base,
  test: {
    ...base.test,
    include: ['test/unit/fixtures/leftoverTimers/*.fixture.ts'],
    isolate: false,
    minThreads: 2,
    maxThreads: 2
  }
})
