import { defineConfig, type UserConfig } from 'vitest/config'
import projectConfig from '../../../../vitest.config'

const base = projectConfig as UserConfig

// Runs the two fixture files of `leftoverTimers.spec.ts` (#551) with the unit tests' setup, in
// shared workers (no isolation), so a worker outlives its file as it can in CI.
export default defineConfig({
  ...base,
  test: {
    ...base.test,
    include: ['test/unit/fixtures/leftoverTimers/*.fixture.ts'],
    isolate: false
  }
})
