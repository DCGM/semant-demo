// @vitest-environment node
// Timers a spec file leaves behind are cleared when it ends (#551, `setup.ts`). Before, such a
// timer threw in the file's worker after its jsdom globals were removed, and the run crashed
// ("Unexpected message from Worker") although every test passed.
import { spawnSync } from 'child_process'
import { resolve } from 'path'
import { expect, it } from 'vitest'

const frontend = resolve(__dirname, '../..')

it('a timer a file leaves behind does not fire into the next part of the run', () => {
  // A run of its own: without this run's Vitest variables, and without colours to match.
  const env: NodeJS.ProcessEnv = { ...process.env, NO_COLOR: '1' }
  for (const key of Object.keys(env)) if (key.startsWith('VITEST')) delete env[key]
  const run = spawnSync(process.execPath,
    [resolve(frontend, 'node_modules/vitest/vitest.mjs'), 'run', '--config', 'test/unit/fixtures/leftoverTimers/vitest.config.ts'],
    { cwd: frontend, env, encoding: 'utf8', timeout: 60_000 })
  const output = `${run.stdout}\n${run.stderr}`

  expect(output).not.toContain('is not defined')
  expect(output).toMatch(/Tests +2 passed/)
  expect(run.status).toBe(0)
}, 70_000)
