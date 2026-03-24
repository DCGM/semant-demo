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

```ts
import { useApi } from 'src/composables/useApi'
import type { Collection } from 'src/generated/api'

const api = useApi().default
const collections = ref<Collection[]>([])

const fetchCollections = async (uId: string) => {
    try {
      	const response = await api.fetchCollectionsApiCollectionsGet({ userId: uId })
      	console.log('Collections fetched:', response)
		collections.value = response.collections
    } catch (error) {...}
}
```