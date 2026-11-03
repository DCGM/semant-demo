import { RouteRecordRaw } from 'vue-router'
import { previewRoutes } from './previewRoutes'

const routes: RouteRecordRaw[] = [
  {
    name: 'default',
    path: '/',
    redirect: '/search/',
    component: () => import('src/app/MainLayout.vue'),
    children: [
      {
        // Kept alive (router/keptPages.ts): a document opened from a result returns to them.
        name: 'search',
        meta: { keepAlive: true },
        path: '/search',
        component: () => import('src/features/search/SearchPage.vue')
      },
      {
        // Kept alive like search: the conversation is there after a cited document.
        name: 'rag',
        meta: { keepAlive: true },
        path: '/rag',
        component: () => import('src/features/rag/RagPage.vue')
      },
      {
        // Document counts of the whole public corpus; no sign-in needed (#254).
        name: 'corpus',
        path: '/corpus',
        component: () => import('src/features/analytics/CorpusOverviewPage.vue')
      },
      {
        // A protected link waiting for a stored session to be verified (router/authGuard.ts).
        name: 'sessionPending',
        path: '/session-pending',
        component: () => import('src/features/auth/SessionPendingPage.vue')
      },
      {
        // The public document view (#545): a corpus document's text and scans, read-only, no
        // sign-in needed. `?page=`, `?chunk=&start=&end=`, `?view=`, `?from=search|chat`.
        name: 'document',
        path: '/documents/:documentId',
        component: () => import('src/features/documents/workspace/PublicDocumentPage.vue'),
        props: true
      },
      {
        name: 'collections',
        meta: { requiresAuth: true },
        path: '/collections',
        component: () => import('src/features/user_collections/UserCollectionsPage.vue')
      },
      {
        name: 'collectionDetail',
        meta: { requiresAuth: true },
        path: '/collections/:collectionId',
        component: () => import('src/features/user_collections/CollectionDetailLayout.vue'),
        props: true,
        redirect: { name: 'collectionOverview' },
        children: [
          {
            name: 'collectionOverview',
            path: 'overview',
            component: () => import('src/features/user_collections/CollectionOverviewPage.vue')
          },
          {
            name: 'collectionDocumentsTagging',
            path: 'documents',
            component: () => import('src/features/user_collections/CollectionDocumentsPage.vue')
          },
          {
            // The collection's annotations as a concordance (KWIC, #329).
            name: 'collectionAnnotations',
            path: 'annotations',
            component: () => import('src/features/annotations/concordance/CollectionAnnotationsPage.vue')
          },
          {
            name: 'collectionTags',
            path: 'tags',
            component: () => import('src/features/user_collections/CollectionTagsAttributesPage.vue')
          },
          {
            // Attribute definitions (#331): what approved annotations are classified by; a
            // part of the Tags & attributes tab.
            name: 'collectionAttributes',
            path: 'attributes',
            component: () => import('src/features/user_collections/CollectionTagsAttributesPage.vue')
          },
          {
            name: 'collectionMembers',
            path: 'members',
            component: () => import('src/features/user_collections/CollectionMembersPage.vue')
          }
        ]
      },
      {
        name: 'documentDetailLayout',
        meta: { requiresAuth: true },
        path: '/collections/:collectionId/documents/:documentId',
        component: () => import('src/features/documents/DocumentPageLayout.vue'),
        props: true,
        redirect: { name: 'documentDetailV1' },
        children: [
          {
            name: 'documentDetailLayoutV1',
            path: 'v1',
            component: () => import('src/features/documents/viewer/DocumentViewLayout.vue'),
            props: true,
            children: [
              {
                name: 'documentDetailV1',
                path: '',
                component: () => import('src/features/documents/viewer/DocumentReaderPage.vue'),
                props: true
              }
            ]
          },
          {
            // The V2 document view was retired in #210; old links open the document view.
            path: 'v2',
            redirect: { name: 'documentDetailV1' }
          }
        ]
      },
      {
        name: 'about',
        path: '/about',
        component: () => import('src/app/AboutPage.vue')
      },
      {
        name: 'feedback',
        path: '/feedback',
        component: () => import('src/features/feedback/FeedbackPage.vue')
      },
      ...previewRoutes(process.env.SEMANT_PREVIEW_ROUTES === '1')
    ]
  },
  // Always leave this as last one,
  // but you can also remove it
  {
    path: '/:catchAll(.*)*',
    component: () => import('src/app/ErrorNotFound.vue')
  }
]

export default routes
