# Image search (image-search-frontend)

Semantic image search

## Install the dependencies
```bash
yarn
# or
npm install
```

### Start the app in development mode (hot-code reloading, error reporting, etc.)
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


### Generating functions and types from backend

`npm run sync-client` (requires running backend) will generate types and function to "/src/generated" folder

For calling the API, use hook `useApi()` in your components, for example:

```ts
const api = useApi()
```