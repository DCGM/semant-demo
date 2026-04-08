import { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    name: 'default',
    path: '/',
    redirect: '/search/',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      {
        name: 'search',
        path: '/search',
        component: () => import('pages/SearchPage.vue')
      },
      {
        name: 'rag',
        path: '/rag',
        component: () => import('pages/RagPage.vue')
      },
      {
        name: 'collections',
        path: '/collections',
        component: () => import('pages/Collections/UserCollectionsPage.vue')
      },
      {
        name: 'collectionDetail',
        path: '/collections/:collectionId',
        component: () => import('layouts/CollectionDetailLayout.vue'),
        props: true,
        redirect: { name: 'collectionOverview' },
        children: [
          {
            name: 'collectionOverview',
            path: 'overview',
            component: () => import('pages/Collections/CollectionOverviewPage.vue')
          },
          {
            name: 'collectionDocumentsTagging',
            path: 'documents',
            component: () => import('src/pages/Collections/CollectionDocumentsTPage.vue')
          },
          {
            name: 'collectionTags',
            path: 'tags',
            component: () => import('pages/Collections/CollectionTagsPage.vue')
          },
          {
            name: 'collectionTaggingJobs',
            path: 'tagging_jobs',
            component: () => import('pages/Collections/CollectionTaggingJobsPage.vue')
          },
          {
            name: 'collectionMembers',
            path: 'members',
            component: () => import('pages/Collections/CollectionMembersPage.vue')
          },
          {
            name: 'documentTagging',
            path: 'documents/:documentId/tagging',
            component: () => import('pages/Collections/DocumentTaggingPage/DocumentTaggingPage.vue'),
            props: true
          },
          {
            name: 'documentDetail',
            path: 'documents/:documentId',
            component: () => import('pages/Collections/DocumentDetailPage.vue'),
            props: true
          }
        ]
      },
      {
        name: 'tagManagement',
        path: '/tag_manage',
        component: () => import('pages/TagManagementPage.vue')
      },
      {
        name: 'about',
        path: '/about',
        component: () => import('pages/AboutPage.vue')
      },
      {
        name: 'feedback',
        path: '/feedback',
        component: () => import('pages/FeedbackPage.vue')
      }
    ]
  },
  // Always leave this as last one,
  // but you can also remove it
  {
    path: '/:catchAll(.*)*',
    component: () => import('pages/ErrorNotFound.vue')
  }
]

export default routes
