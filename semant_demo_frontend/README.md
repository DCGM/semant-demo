# semANT demo frontend

Vue 3 + Quasar SPA. Shared setup and requirements:
[CONTRIBUTING.md](../CONTRIBUTING.md#2-setup-and-commands); structure:
[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md#3-frontend-semant_demo_frontend).
Use Node 22 (`.nvmrc`). Commands below run in `semant_demo_frontend` unless stated otherwise.

## Install the dependencies

```bash
npm ci
```

Versions are pinned by `package-lock.json`; preserve it unless deliberately upgrading.
Vitest 0.23 is the last line supporting the Vite 2 used by `@quasar/app-vite` 1.

### Start the app in development mode (hot-code reloading, error reporting, etc.)

Prefer the [seeded local application](../docs/DEVELOPMENT.md#1-quick-start-the-seeded-local-application)
(`make dev-up`, `make dev-backend`, `make dev-frontend` from the repository root). The
frontend-only equivalent is:

```bash
npm run dev
```

### Checks

```bash
npm run lint        # ESLint
npm run typecheck   # vue-tsc against typecheck-baseline.json (empty: no known errors)
npm test            # Vitest unit/component tests (test/unit)
npm run api-check   # generated client drift; requires backend .venv and Java 11+
```

New type errors fail: never add baseline entries to make checks pass. ESLint warnings are
reported but do not fail; errors do. Core `no-undef` checks JavaScript only because it
misreads TypeScript type names. `vue-tsc` checks TypeScript/Vue; components must use
`<script lang="ts">` (lint-enforced). `test/unit/devTooling.spec.ts` covers both defaults.
Unit/component tests use Vitest and Vue Test Utils under `test/unit`.

For targeted iteration use `npx vitest run test/unit/routes.spec.ts`. For browser tests,
use the [fast loop](../docs/DEVELOPMENT.md#fast-browser-test-loop) from the repository root,
e.g. `make e2e-dev-test ARGS="test/e2e/<spec>.spec.ts"`. Run the fresh `make test-e2e` as
required by [the testing contract](../CONTRIBUTING.md#4-testing-contract), not after every
edit. It builds the frontend, starts the isolated seeded backend and uses fake AI.

Without Make, the full browser-test equivalent (from the repository root, after setup) is:

```bash
(cd semant_demo_frontend && npx playwright install --only-shell chromium)
scripts/with-test-weaviate.sh sh -c 'cd semant_demo_frontend && env -u DISPLAY PYTHON=../.venv/bin/python npm run test:e2e'
```

This requires Docker; bare `npm run test:e2e` is not a substitute for the isolated profile.
UI inspection and screenshot uploads: [UI checklist](../docs/UI_GUIDELINES.md#ui-change-checklist).

### API client generation

The generated client (`src/generated/api`) is committed; never edit it by hand. After a
backend API change, run `make api-generate` from the repository root, or `npm run
api-generate` here. `make api-check` / `npm run api-check` detect drift. Generation starts
with an empty output directory so stale files disappear. Review the generated diff and
include caller/contract changes. Stream events also need tests; generation does not verify
them. The production image builds the committed client with `npm ci`, without regeneration.

Without `PYTHON`, `scripts/api-client.sh` uses the repository `.venv/bin/python` from any
directory and stops with instructions if it or backend dependencies are missing, rather
than choosing `python` from `PATH`. An explicit relative `PYTHON` path is resolved from
the script's starting directory (`semant_demo_frontend` under `npm run`).

The pinned generator in `openapitools.json` runs through `npx --no-install
openapi-generator-cli` and needs Java 11+ on `PATH`. Its first run downloads the pinned jar
(~31 MB); subsequent runs are offline. CI sets `OPENAPI_GENERATOR` to that version's jar.
Preserve the generator pin unless explicitly upgrading.

### Build the app for production

```bash
npx quasar build
```

### Customize the configuration

See [Configuring quasar.config.js](https://v2.quasar.dev/quasar-cli-vite/quasar-config-js).

### Call API functions

All requests go through `src/shared/api` (one backend URL, the signed-in user's token,
common error handling); do not create another HTTP client.

```ts
import { ref } from 'vue'
import { apiErrorMessage, useApi } from 'src/shared/api'
import type { Collection } from 'src/generated/api'

const api = useApi().default
const collections = ref<Collection[]>([])

const fetchCollections = async () => {
  try {
    collections.value = await api.fetchCollectionsApiUserCollectionsGet()
  } catch (error) {
    console.error(await apiErrorMessage(error, 'Failed to load collections'))
  }
}
```

NDJSON streams use `postNdjson(path, body, { onValue, signal })` from the same module.
