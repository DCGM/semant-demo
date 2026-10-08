# Image search (image-search-frontend)

Semantic image search

## Install the dependencies
```bash
yarn
# or
npm install
```

### Start the app in development mode (hot-code reloading, error reporting, etc.)

**Before running the app in development mode, backend types and functions need be generated.**
1. activate virtual environment
2. run `npm run sync-client` in the frontend folder (requires Java installed)

```bash
quasar dev
```


### Lint the files
```bash
yarn lint
# or
npm run lint
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