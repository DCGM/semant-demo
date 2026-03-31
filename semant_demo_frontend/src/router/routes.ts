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
        name: 'tag',
        path: '/tag',
        component: () => import('pages/TaggingPage.vue')
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
            component: () => import('pages/Collections/CollectionDocumentsTaggingPage.vue')
          },
          {
            name: 'collectionTags',
            path: 'tags',
            component: () => import('pages/Collections/CollectionTagsPage.vue')
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
          }
        ]
      },
      {
        name: 'tagging',
        path: '/tagging',
        component: () => import('pages/TaggingPage/TaggingPage.vue')
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
