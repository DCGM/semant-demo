# SemANT demo frontend

Vue 3 + Quasar SPA (package name `image-search-frontend` is historical). Setup, checks and
client generation are described in [CONTRIBUTING.md](../CONTRIBUTING.md#2-setup-and-commands);
the structure in [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md#3-frontend-semant_demo_frontend).

## Install the dependencies
```bash
npm ci
```

### Start the app in development mode (hot-code reloading, error reporting, etc.)

The generated API client (`src/generated/api`) is committed. After a backend API change,
regenerate it from the repository root with `make api-generate` (requires Java 11+); never
edit it by hand. The production image (`deploy/Dockerfile`) builds from this committed
client with `npm ci`; it does not regenerate it.

```bash
npm run dev
```

### Checks
```bash
npm run lint        # ESLint
npm run typecheck   # vue-tsc against typecheck-baseline.json (empty: no known errors)
npm test            # Vitest unit/component tests (test/unit)
npm run test:e2e    # Playwright smoke suite; use `make test-e2e` from the root (needs Docker)
```

### Build the app for production
```bash
quasar build
```

### Customize the configuration
See [Configuring quasar.config.js](https://v2.quasar.dev/quasar-cli-vite/quasar-config-js).


### Call API functions

All requests go through `src/shared/api` (one backend URL, the signed-in user's token,
common error handling); do not create another HTTP client.

```ts
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