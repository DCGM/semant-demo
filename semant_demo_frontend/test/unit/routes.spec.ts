import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter, type RouteComponent, type RouteRecordRaw } from 'vue-router'

import routes from 'src/router/routes'

function makeRouter () {
  return createRouter({ history: createMemoryHistory(), routes })
}

function lazyComponents (records: RouteRecordRaw[]): (() => Promise<RouteComponent>)[] {
  return records.flatMap((record) => [
    ...('component' in record && typeof record.component === 'function'
      ? [record.component as () => Promise<RouteComponent>]
      : []),
    ...lazyComponents(record.children ?? [])
  ])
}

describe('routes', () => {
  it.each([
    ['/search', 'search', false],
    ['/rag', 'rag', false],
    ['/corpus', 'corpus', false],
    ['/collections', 'collections', true],
    ['/collections/c1', 'collectionOverview', true],
    ['/collections/c1/overview', 'collectionOverview', true],
    ['/collections/c1/documents', 'collectionDocumentsTagging', true],
    ['/collections/c1/annotations', 'collectionAnnotations', true],
    ['/collections/c1/tags', 'collectionTags', true],
    ['/collections/c1/members', 'collectionMembers', true],
    ['/collections/c1/documents/d1', 'documentDetailV1', true],
    ['/collections/c1/documents/d1/v1', 'documentDetailV1', true],
    ['/collections/c1/documents/d1/v2', 'documentDetailV1', true],
    ['/feedback', 'feedback', false],
    ['/about', 'about', false]
  ])('resolve the deep link %s', async (path, name, requiresAuth) => {
    const router = makeRouter()
    await router.push(path)

    const route = router.currentRoute.value
    expect(route.name).toBe(name)
    expect(Boolean(route.meta.requiresAuth)).toBe(requiresAuth)
    if (path.startsWith('/collections/')) expect(route.params.collectionId).toBe('c1')
    if (path.includes('/documents/d1')) expect(route.params.documentId).toBe('d1')
  })

  it('redirect the root to search and unknown paths to the not-found page', async () => {
    const router = makeRouter()
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('search')

    await router.push('/no/such/page')
    expect(router.currentRoute.value.matched).toHaveLength(1)
    expect(router.currentRoute.value.matched[0].path).toBe('/:catchAll(.*)*')
  })

  it('load every page component', async () => {
    const loaders = lazyComponents(routes)
    expect(loaders.length).toBeGreaterThan(10)
    for (const load of loaders) {
      const module = await load() as { default?: unknown }
      expect(module.default).toBeTruthy()
    }
  })
})
