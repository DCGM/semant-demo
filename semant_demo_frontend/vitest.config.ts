import path from 'path'
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

// Unit/component tests run in jsdom without the Quasar CLI. Keep the aliases in
// line with @quasar/app-vite/tsconfig-preset.json.
const src = path.resolve(__dirname, 'src')

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      // Node resolution would pick Quasar's server-side CommonJS build.
      quasar: 'quasar/dist/quasar.esm.prod.js',
      src,
      components: `${src}/components`,
      layouts: `${src}/layouts`,
      pages: `${src}/pages`,
      assets: `${src}/assets`,
      boot: `${src}/boot`,
      stores: `${src}/stores`
    }
  },
  test: {
    environment: 'jsdom',
    include: ['test/unit/**/*.spec.ts'],
    // Generated client and build output are not test sources.
    exclude: ['node_modules', 'dist', 'src/generated/**']
  }
})
