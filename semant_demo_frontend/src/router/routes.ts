import { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    name: 'default',
    path: '/',
    redirect: '/search/',
    component: () => import('src/app/MainLayout.vue'),
    children: [
      {
        name: 'search',
        path: '/search',
        component: () => import('src/features/search/SearchPage.vue')
      },
      {
        name: 'rag',
        path: '/rag',
        component: () => import('src/features/rag/RagPage.vue')
      },
      {
        // A protected link waiting for a stored session to be verified (router/authGuard.ts).
        name: 'sessionPending',
        path: '/session-pending',
        component: () => import('src/features/auth/SessionPendingPage.vue')
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
            name: 'collectionTags',
            path: 'tags',
            component: () => import('src/features/user_collections/CollectionTagsPage.vue')
          },
          {
            name: 'collectionTaggingJobs',
            path: 'tagging_jobs',
            component: () => import('src/features/user_collections/CollectionTaggingJobsPage.vue')
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
      }
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
