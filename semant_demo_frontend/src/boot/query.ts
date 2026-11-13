import { boot } from 'quasar/wrappers'
import { VueQueryPlugin } from '@tanstack/vue-query'
import { queryClient } from 'src/shared/query'

// Registers the one query client (`shared/query.ts`) with the app.
export default boot(({ app }) => {
  app.use(VueQueryPlugin, { queryClient })
})
