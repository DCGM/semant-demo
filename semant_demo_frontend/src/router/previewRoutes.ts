import type { RouteRecordRaw } from 'vue-router'

/**
 * Pages that show a component before a product view uses it, for development and browser
 * tests. They are built only with `SEMANT_PREVIEW_ROUTES=1` (quasar.config.js: the dev
 * server and the browser-test builds), never linked, and removed once the component has its
 * place in the application.
 */
export function previewRoutes (enabled: boolean): RouteRecordRaw[] {
  if (!enabled) return []
  return [
    {
      // The scan viewer (#543) on its own, until the paired document workspace (#545).
      name: 'previewScanViewer',
      path: '/preview/scan/:documentId',
      component: () => import('src/features/documents/scan/ScanPreviewPage.vue'),
      props: true
    },
    {
      // The text and scan panes with their correspondence (#544), until #545.
      name: 'previewTextScan',
      path: '/preview/text-scan/:documentId',
      component: () => import('src/features/documents/correspondence/TextScanPreviewPage.vue'),
      props: true
    }
  ]
}
