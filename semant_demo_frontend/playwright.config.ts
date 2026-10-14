import { defineConfig, devices } from '@playwright/test'
import { viewports, type ViewportName } from './test/e2e/viewports'

// Browser smoke tests (`make test-e2e`). The web server builds the frontend into
// dist/e2e and starts the deterministic backend profile (semant_demo_backend/tests/e2e_server.py),
// which seeds the fixture corpus into a test-owned Weaviate and fakes AI providers.
// SEMANT_TEST_WEAVIATE_* must point at such a store (scripts/with-test-weaviate.sh).

const port = Number(process.env.E2E_PORT || 8765)
const baseURL = `http://127.0.0.1:${port}`
// Resolved from semant_demo_backend; the Makefile passes an absolute path.
const python = process.env.PYTHON || '../.venv/bin/python'
// scripts/e2e-dev.sh: the profile already runs; never start (build, seed) another one.
const externalServer = process.env.E2E_EXTERNAL_SERVER === '1'
// scripts/e2e-dev.sh capture: screenshots and traces at the three layouts reviewed for UI work.
const capture = process.env.E2E_CAPTURE === '1'
// They run the selected browser specs plus the view captures in test/capture (not test/unit).
const captureProject = (name: ViewportName) => ({
  name,
  testDir: './test',
  testIgnore: 'unit/**',
  use: { ...devices['Desktop Chrome'], viewport: viewports[name], screenshot: 'on', trace: 'on' } as const
})

export default defineConfig({
  testDir: './test/e2e',
  // All tests share one seeded backend; keep them sequential and independent of order.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL,
    trace: 'retain-on-failure'
  },
  projects: capture
    ? [captureProject('wide'), captureProject('narrow'), captureProject('phone')]
    : [
        { name: 'chromium', use: { ...devices['Desktop Chrome'] } }
      ],
  webServer: externalServer ? undefined : {
    command: [
      'npx quasar build',
      `cd ../semant_demo_backend && ${python} -m tests.e2e_server --port ${port} --static ../semant_demo_frontend/dist/e2e`
    ].join(' && '),
    url: `${baseURL}/health`,
    env: { BACKEND_URL: baseURL, QUASAR_DIST_DIR: 'dist/e2e' },
    timeout: 240_000,
    // Set E2E_REUSE_SERVER=1 to iterate against an e2e_server you started yourself.
    reuseExistingServer: process.env.E2E_REUSE_SERVER === '1',
    // SIGTERM (not the default SIGKILL) lets the profile remove its temporary files.
    gracefulShutdown: { signal: 'SIGTERM', timeout: 10_000 },
    stdout: 'ignore',
    stderr: 'pipe'
  }
})
