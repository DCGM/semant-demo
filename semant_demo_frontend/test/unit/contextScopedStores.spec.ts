import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { effectScope } from 'vue'

import { useTagSpansStore } from 'src/stores/tagSpansStore'
import { useTagsStore } from 'src/stores/tagsStore'
import { useCollectionsStore } from 'src/stores/collectionsStore'
import { useDocumentsStore } from 'src/stores/documentsStore'
import { useUserStore } from 'src/stores/user-store'
import { useSessionScope } from 'src/app/session'
import { WriteOutcome } from 'src/generated/api'

// Requests the test resolves by hand, in any order.
type Deferred<T> = { promise: Promise<T>, resolve: (value: T) => void, reject: (e: unknown) => void }
function deferred<T> (): Deferred<T> {
  let resolve!: (value: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((_resolve, _reject) => {
    resolve = _resolve
    reject = _reject
  })
  return { promise, resolve, reject }
}

// Pending requests per key, oldest first: `answer`/`fail` settle the oldest one.
const pending = new Map<string, Deferred<unknown>[]>()
function request<T> (key: string): Promise<T> {
  const d = deferred<T>()
  pending.set(key, [...(pending.get(key) ?? []), d as Deferred<unknown>])
  return d.promise
}
function next (key: string): Deferred<unknown> {
  const queue = pending.get(key)
  const d = queue?.shift()
  if (!d) throw new Error(`no pending request ${key}`)
  return d
}
function answer (key: string, value: unknown) {
  next(key).resolve(value)
}
function fail (key: string, error: unknown) {
  next(key).reject(error)
}

vi.mock('src/repositories/useTagSpansRepository', () => ({
  useTagSpansRepository: () => ({
    getByChunkIdsInCollection: (chunkIds: string[], collectionId: string) => request(`spans:${collectionId}`),
    getByChunkIdInCollection: (chunkId: string, collectionId: string) => request(`span:${collectionId}:${chunkId}`),
    create: () => request('create'),
    delete: () => request('delete')
  })
}))
vi.mock('src/repositories/useTagsRepository', () => ({
  useTagsRepository: () => ({ getAllByCollection: (collectionId: string) => request(`tags:${collectionId}`) })
}))
vi.mock('src/repositories/useCollectionRepository', () => ({
  useCollectionRepository: () => ({
    getAll: () => request('collections'),
    getById: (collectionId: string) => request(`collection:${collectionId}`)
  })
}))
vi.mock('src/repositories/useDocumentsRepository', () => ({
  useDocumentsRepository: () => ({
    getAllByCollection: (collectionId: string) => request(`documents:${collectionId}`),
    getById: (documentId: string) => request(`document:${documentId}`),
    removeFromCollection: (documentId: string) => request(`remove:${documentId}`)
  })
}))
vi.mock('src/utils/notification', () => {
  const notif = { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() }
  return { ongoingNotification: () => notif, warningNotification: vi.fn(), notif }
})

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))
const span = (id: string, chunkId: string) => ({ id, chunkId, tagId: 't', start: 0, end: 1, type: 'pos' })
const complete = { outcome: WriteOutcome.complete, succeeded: [], failed: [], unattempted: [] }

beforeEach(() => {
  setActivePinia(createPinia())
  pending.clear()
})

describe('span store scope', () => {
  it('drops spans of a collection the view has left, also for a shared chunk', async () => {
    const store = useTagSpansStore()
    const loadA = store.fetchSpansForChunksInCollection(['shared-chunk'], 'A')
    const loadB = store.fetchSpansForChunksInCollection(['shared-chunk'], 'B')

    answer('spans:B', { 'shared-chunk': [span('b-span', 'shared-chunk')] })
    await loadB
    answer('spans:A', { 'shared-chunk': [span('a-span', 'shared-chunk')] })
    await loadA

    expect(store.spansByChunkId['shared-chunk'].map((s) => s.id)).toEqual(['b-span'])
    expect(store.loading).toBe(false)
  })

  it('keeps the newer load in progress when an older one finishes', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const store = useTagSpansStore()
    void store.fetchSpansForChunksInCollection(['c1'], 'A')
    store.clearAll() // document changed
    const current = store.fetchSpansForChunksInCollection(['c2'], 'A')

    fail('spans:A', new Error('late failure'))
    await flush()
    expect([store.loading, store.error]).toEqual([true, null])

    answer('spans:A', { c2: [span('s2', 'c2')] })
    await current
    expect(store.spansByChunkId).toEqual({ c2: [span('s2', 'c2')] })
  })

  it('does not add a span saved for the previous document to the current one', async () => {
    const store = useTagSpansStore()
    const loading = store.fetchSpansForChunksInCollection(['c1'], 'A')
    answer('spans:A', { c1: [] })
    await loading

    const saving = store.createSpan({ chunkId: 'c1', tagId: 't', start: 0, end: 1, type: 'pos' })
    store.clearAll()
    answer('create', { ...span('saved', 'c1'), ...complete })
    await saving

    expect(store.spansByChunkId).toEqual({})
  })
})

describe('tag store scope', () => {
  it('shows no tags of the previous collection, early or late', async () => {
    const store = useTagsStore()
    const loadA = store.fetchTagsByCollection('A')
    answer('tags:A', [{ id: 'a-tag' }])
    await loadA

    const loadB = store.fetchTagsByCollection('B')
    expect(store.tags).toEqual([]) // not A's tags while B loads
    void store.fetchTagsByCollection('A') // back and forth quickly
    const loadB2 = store.fetchTagsByCollection('B')

    answer('tags:B', [{ id: 'b-tag-old' }]) // first load of B: superseded by the second
    answer('tags:B', [{ id: 'b-tag' }])
    await Promise.all([loadB, loadB2])
    answer('tags:A', [{ id: 'a-tag' }])
    await flush()

    expect(store.tags.map((t) => t.id)).toEqual(['b-tag'])
    expect(store.loading).toBe(false)
  })
})

describe('open collection and document', () => {
  it('never shows the metadata or rights of the previously opened collection', async () => {
    const store = useCollectionsStore()
    const loadA = store.fetchCollection('A')
    answer('collection:A', { id: 'A', isSharedWithMe: false })
    await loadA

    const loadB = store.fetchCollection('B')
    expect(store.activeCollection).toBeNull()
    answer('collection:B', { id: 'B', isSharedWithMe: true })
    await loadB
    expect(store.activeCollection).toEqual({ id: 'B', isSharedWithMe: true })
  })

  it('ignores a late document answer after switching documents', async () => {
    const store = useDocumentsStore()
    const first = store.fetchDocument('d1')
    const second = store.fetchDocument('d2')
    answer('document:d2', { id: 'd2' })
    await second
    answer('document:d1', { id: 'd1' })
    await first

    expect(store.activeDocument).toEqual({ id: 'd2' })
  })
})

describe('partial bulk removal', () => {
  it('removes only the documents whose removal the backend acknowledged', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const store = useDocumentsStore()
    const load = store.fetchDocumentsByCollection('A')
    answer('documents:A', [{ id: 'd1' }, { id: 'd2' }, { id: 'd3' }])
    await load

    const removing = store.removeManyFromCollection(['d1', 'd2'], 'A')
    expect(store.documents.map((d) => d.id)).toEqual(['d3']) // hidden while pending
    answer('remove:d1', complete)
    fail('remove:d2', new Error('500'))
    await removing

    expect(store.documents.map((d) => d.id)).toEqual(['d2', 'd3'])
    expect(store.error).toBe('Failed to remove selected documents from collection')
  })
})

describe('session scope', () => {
  it('clears user data on logout and ignores answers to the old user\'s requests', async () => {
    // useSessionScope sets up a watcher; run it in an effect scope like App.vue's setup.
    const scope = effectScope()
    scope.run(useSessionScope)

    const user = useUserStore()
    user.user = { id: 'u1', email: 'u1@example.com' }
    await flush()

    const collections = useCollectionsStore()
    const tags = useTagsStore()
    const spans = useTagSpansStore()
    const listing = collections.fetchCollections()
    answer('collections', [{ id: 'A' }])
    await listing
    const loadingTags = tags.fetchTagsByCollection('A')
    const loadingSpans = spans.fetchSpansForChunksInCollection(['c1'], 'A')

    user.user = null // logout
    await flush()
    answer('tags:A', [{ id: 'a-tag' }])
    answer('spans:A', { c1: [span('s1', 'c1')] })
    await Promise.all([loadingTags, loadingSpans])

    expect([collections.collections, tags.tags, spans.spansByChunkId]).toEqual([[], [], {}])
    scope.stop()
  })

  it('keeps data loaded with the stored token while the session is being restored', async () => {
    const scope = effectScope()
    scope.run(useSessionScope)
    const collections = useCollectionsStore()
    const listing = collections.fetchCollections()
    answer('collections', [{ id: 'A' }])
    await listing

    useUserStore().user = { id: 'u1', email: 'u1@example.com' } // /users/me answered
    await flush()

    expect(collections.collections.map((c) => c.id)).toEqual(['A'])
    scope.stop()
  })
})
