import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { Quasar } from 'quasar'

import SavedFilterHeader from 'src/features/annotations/concordance/SavedFilterHeader.vue'
import SavedFiltersMenu from 'src/features/annotations/concordance/SavedFiltersMenu.vue'

import { defaultFilters, useConcordanceStore, withMode, type ConcordanceFilters } from 'src/features/annotations/concordance/concordanceStore'
import {
  filtersOf, liveQueryOf, missingReferences, missingText, sameQuery
} from 'src/features/annotations/concordance/savedFilters'
import { useSavedFiltersStore } from 'src/features/annotations/concordance/savedFiltersStore'
import { AnnotationSort, SpanType, TextScope, type Attribute, type SavedSelection, type Tag } from 'src/generated/api'
import { endSession } from 'src/shared/api'

// Saved live filters of the annotation workspace (#824): what is kept of the workspace and how
// it is restored, when the workspace counts as changed, which deleted tags and attributes a live
// filter still names, and the store's list, open, save, update, rename and delete.

const filters = (change: Partial<ConcordanceFilters> = {}): ConcordanceFilters => ({ ...defaultFilters(), ...change })
const ATTRIBUTE: Attribute = {
  id: 'attr-1',
  name: 'speaker',
  cardinality: 'single',
  allTags: true,
  tagIds: [],
  revision: 1,
  values: [{ id: 'val-1', label: 'Woman' }]
} as Attribute
const TAGS = [{ id: 'tag-1', name: 'Osoba' }] as Tag[]

describe('live queries', () => {
  it('keeps the query, order and columns and restores them, without a Find similar source', () => {
    const f = filters({
      tagIds: ['tag-1'],
      types: [SpanType.pos],
      text: ' Praha ',
      textScope: TextScope.both,
      documentIds: ['doc-1'],
      documentFilters: { yearMin: 1900 },
      attributeValues: ['attr-1:val-1'],
      attributeUnassigned: ['attr-2'],
      sort: AnnotationSort.attribute,
      sortAttribute: 'attr-1',
      descending: true
    })
    const q = liveQueryOf(f, ['attr-1'])
    expect(q).toMatchObject({
      filters: { tagIds: ['tag-1'], types: ['pos'], q: 'Praha', textScope: 'both', documentIds: ['doc-1'], documentFilters: { yearMin: 1900 } },
      sort: 'attribute',
      sortAttribute: 'attr-1',
      descending: true,
      shownAttributeIds: ['attr-1']
    })
    expect(filtersOf(q)).toEqual({ ...f, text: 'Praha' })

    const similar = liveQueryOf(filters({ similarTo: { id: 'row-1' } as never, mode: 'similar' as never }), [])
    expect(similar.filters?.rankingQuery).toBeNull()
    expect(filtersOf(similar).similarTo).toBeNull()
    const ranked = filtersOf(liveQueryOf(filters({ similarity: 'válka', mode: 'hybrid' as never }), []))
    expect(ranked.similarity).toBe('válka')
  })

  it('restores a similarity text as a ranked query that compares equal to itself (#828 review)', () => {
    const q = liveQueryOf(withMode({ ...defaultFilters(), similarity: 'válka' }), [])
    expect(q.filters?.rankingQuery).toBe('válka')
    expect(filtersOf(q)).toMatchObject({ similarity: 'válka', mode: 'hybrid' })
    expect(sameQuery(q, q)).toBe(true)
    expect(sameQuery(liveQueryOf(withMode({ ...defaultFilters(), similarity: 'mír' }), []), q)).toBe(false)
  })

  it('compares queries as sets, ignoring empty fields', () => {
    const saved = liveQueryOf(filters({ tagIds: ['b', 'a'], types: [SpanType.auto, SpanType.pos] }), ['x', 'y'])
    expect(sameQuery(liveQueryOf(filters({ tagIds: ['a', 'b'] }), ['y', 'x']), saved)).toBe(true)
    expect(sameQuery(liveQueryOf(filters({ tagIds: ['a', 'b'], text: 'Brno' }), ['x', 'y']), saved)).toBe(false)
    expect(sameQuery(liveQueryOf(filters({ tagIds: ['a', 'b'], descending: true }), ['x', 'y']), saved)).toBe(false)
    expect(sameQuery(liveQueryOf(filters({ tagIds: ['a', 'b'] }), ['x']), saved)).toBe(false)
    // What the server echoes, with defaults spelled out, is the same query.
    expect(sameQuery(liveQueryOf(filters(), []), { filters: { attributeValues: [], documentFilters: {} }, sort: AnnotationSort.document })).toBe(true)
  })

  it('counts the deleted tags, attributes and values a live filter names', () => {
    const q = liveQueryOf(filters({
      tagIds: ['tag-1', 'gone-tag'],
      attributeValues: ['attr-1:val-1', 'attr-1:gone-value', 'gone-attr:v'],
      near: { tagIds: ['gone-tag-2'] },
      sort: AnnotationSort.attribute,
      sortAttribute: 'gone-attr'
    }), ['attr-1'])
    const missing = missingReferences(q, TAGS, [ATTRIBUTE])
    expect(missing).toEqual({ tags: 2, attributes: 1, values: 1 })
    expect(missingText(missing)).toBe('This live filter refers to 2 deleted tags, 1 deleted attribute, 1 deleted attribute value, ' +
      'which no annotation can match. Update it to save the current filters.')
    expect(missingText(missingReferences(liveQueryOf(filters({ tagIds: ['tag-1'] }), []), TAGS, [ATTRIBUTE]))).toBeNull()
  })
})

const saved = (id: string, name: string, change: Partial<ConcordanceFilters> = {}, extra: Partial<SavedSelection> = {}): SavedSelection => ({
  id,
  collectionId: 'col-1',
  kind: 'live',
  name,
  query: liveQueryOf(filters(change), []),
  unreadable: false,
  createdBy: 'u1',
  updatedBy: 'u1',
  createdAt: new Date(),
  updatedAt: new Date(),
  canEdit: true,
  ...extra
} as SavedSelection)

/** Answers each request at once: saved filters from `responses`, annotation reads empty. */
function fakeServer (responses: Record<string, (body: unknown) => [unknown, number?]>) {
  const requests: { method: string, path: string, body: unknown }[] = []
  const fetchMock = vi.fn((input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => {
    const url = new URL(String(input))
    const method = init?.method ?? 'GET'
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined
    requests.push({ method, path: url.pathname, body })
    const handler = responses[`${method} ${url.pathname}`]
    const empty = url.pathname.endsWith('/annotations')
      ? { rows: [], total: 0, offset: 0, limit: 50 }
      : url.pathname.endsWith('/facets') ? { population: 'filtered', self_exclusion: true, facets: [] } : []
    const [answer, status] = handler ? handler(body) : [empty, 200]
    return Promise.resolve(status === 204
      ? new Response(null, { status })
      : new Response(JSON.stringify(answer), { status: status ?? 200, headers: { 'Content-Type': 'application/json' } }))
  })
  return { requests, fetchMock }
}

describe('saved filters store', () => {
  const originalFetch = globalThis.fetch
  const base = '/api/user_collections/col-1/saved-selections'
  const wire = (s: SavedSelection) => ({
    id: s.id,
    collection_id: s.collectionId,
    kind: s.kind,
    name: s.name,
    unreadable: s.unreadable,
    can_edit: s.canEdit,
    created_by: s.createdBy,
    updated_by: s.updatedBy,
    created_at: '2026-11-20T10:00:00Z',
    updated_at: '2026-11-20T10:00:00Z',
    query: s.query && {
      filters: { tag_ids: s.query.filters?.tagIds ?? null, types: s.query.filters?.types, q: s.query.filters?.q ?? null },
      sort: s.query.sort,
      sort_attribute: s.query.sortAttribute ?? null,
      descending: s.query.descending,
      shown_attribute_ids: []
    }
  })

  beforeEach(() => { setActivePinia(createPinia()) })
  afterEach(() => { globalThis.fetch = originalFetch })

  async function opened (responses: Record<string, (body: unknown) => [unknown, number?]>) {
    const server = fakeServer(responses)
    globalThis.fetch = server.fetchMock as typeof fetch
    const concordance = useConcordanceStore()
    await concordance.open('col-1')
    const store = useSavedFiltersStore()
    await store.load('col-1')
    return { store, concordance, server }
  }

  it('lists by name, opens a live filter as a fresh query and notices later changes', async () => {
    const speakers = saved('s1', 'speakers', { tagIds: ['tag-1'], text: 'Praha' })
    const { store, concordance, server } = await opened({
      [`GET ${base}`]: () => [[wire(saved('s2', 'Zebra')), wire(speakers)]]
    })
    expect(store.items.map(s => s.name)).toEqual(['speakers', 'Zebra'])

    await store.open(store.items[0]!)
    expect(store.activeId).toBe('s1')
    expect(concordance.filters).toMatchObject({ tagIds: ['tag-1'], text: 'Praha' })
    const read = server.requests.filter(r => r.path.endsWith('/annotations')).at(-1)!
    expect(read.path).toBe('/api/user_collections/col-1/annotations')
    expect(store.modified).toBe(false)

    await concordance.setFilters({ text: 'Brno' })
    expect(store.modified).toBe(true)
    await concordance.setFilters({ text: 'Praha' })
    expect(store.modified).toBe(false)

    concordance.shownAttributeIds = ['attr-1']
    await concordance.setFilters({ text: 'Brno' })
    await store.discard() // back to the filters as saved
    expect(concordance.filters).toMatchObject({ tagIds: ['tag-1'], text: 'Praha' })
    expect(store.modified).toBe(false)

    await store.close() // the open one clicked again: back to the default filters and columns
    expect(store.activeId).toBeNull()
    expect(concordance.filters).toEqual(defaultFilters())
    expect(concordance.shownAttributeIds).toEqual([])
  })

  it('opens, changes and discards a saved similarity text without a false change; Find similar is never saved', async () => {
    const ranked = { ...saved('s1', 'War'), query: liveQueryOf(withMode({ ...defaultFilters(), similarity: 'válka' }), []) }
    const { store, concordance } = await opened({ [`GET ${base}`]: () => [[wire(ranked)]] })
    store.items = [ranked]
    await store.open(ranked)
    expect(concordance.filters).toMatchObject({ similarity: 'válka', mode: 'hybrid' })
    expect(store.modified).toBe(false)
    await concordance.setFilters({ similarity: 'mír' })
    expect(store.modified).toBe(true)
    await store.discard()
    expect(concordance.filters.similarity).toBe('válka')
    expect(store.modified).toBe(false)

    expect(store.savable).toBe(true)
    concordance.filters = { ...concordance.filters, similarTo: { id: 'row-1' } as never, mode: 'similar' as never }
    expect(store.modified).toBe(true) // the saved filter does not hold this source
    expect(store.savable).toBe(false)
  })

  it('saves the current filters as the active live filter and updates it', async () => {
    let created: SavedSelection | null = null
    const { store, concordance, server } = await opened({
      [`GET ${base}`]: () => [[]],
      [`POST ${base}`]: (body) => {
        created = saved('new', (body as { name: string }).name, { text: 'Lhota' })
        return [wire(created), 201]
      },
      [`PATCH ${base}/new`]: () => [wire(saved('new', 'Lhota', { text: 'Lhota', tagIds: ['tag-1'] }))]
    })
    await concordance.setFilters({ text: 'Lhota' })
    await store.saveAs('Lhota')
    const post = server.requests.find(r => r.method === 'POST' && r.path === base)!
    expect(post.body).toMatchObject({ name: 'Lhota', query: { filters: { q: 'Lhota' }, sort: 'document' } })
    expect(store.activeId).toBe('new')
    expect(store.modified).toBe(false)

    await concordance.setFilters({ tagIds: ['tag-1'] })
    expect(store.modified).toBe(true)
    await store.update('new')
    expect(server.requests.find(r => r.method === 'PATCH')!.body).toMatchObject({ query: { filters: { tag_ids: ['tag-1'] } } })
    expect(store.modified).toBe(false)
  })

  it('reports refused writes with the server message and keeps the list', async () => {
    const { store } = await opened({
      [`GET ${base}`]: () => [[wire(saved('s1', 'Speakers', {}, { canEdit: false }))]],
      [`POST ${base}`]: () => [{ detail: 'A saved selection with this name already exists in the collection' }, 400],
      [`DELETE ${base}/s1`]: () => [{ detail: 'Only the creator of a saved selection and the collection owner can change or delete it' }, 403]
    })
    await expect(store.saveAs('speakers')).rejects.toThrow('already exists')
    await expect(store.remove('s1')).rejects.toThrow('Only the creator')
    expect(store.items.map(s => s.id)).toEqual(['s1'])
  })

  it('deletes and renames, and forgets everything for another collection or a sign-out', async () => {
    const { store } = await opened({
      [`GET ${base}`]: () => [[wire(saved('s1', 'Speakers')), wire(saved('s2', 'Places'))]],
      [`PATCH ${base}/s2`]: () => [wire(saved('s2', 'Arenas'))],
      [`DELETE ${base}/s1`]: () => [null, 204],
      'GET /api/user_collections/col-2/saved-selections': () => [[]]
    })
    await store.open(store.items.find(s => s.id === 's1')!)
    await store.remove('s1')
    expect(store.activeId).toBeNull()
    await store.rename('s2', 'Arenas')
    expect(store.items.map(s => s.name)).toEqual(['Arenas'])

    await store.load('col-2')
    expect(store.items).toEqual([])
    await store.load('col-1')
    store.clear()
    endSession()
    expect(store.items).toEqual([])
    expect(store.collectionId).toBeNull()
  })
})

describe('open saved filter header', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  const header = () => mount(SavedFilterHeader, {
    props: { tags: TAGS, attributes: [ATTRIBUTE], definitionsReady: true },
    global: { plugins: [[Quasar, {}]] }
  })
  const find = (wrapper: ReturnType<typeof header>, id: string) => wrapper.find(`[data-testid="${id}"]`)

  it('appears only for an open saved filter and shows whether it changed, what is deleted and who may save', async () => {
    const concordance = useConcordanceStore()
    const store = useSavedFiltersStore()
    const wrapper = header()
    expect(find(wrapper, 'saved-filter-header').exists()).toBe(false)

    store.items = [saved('s1', 'Praha', { text: 'Praha', tagIds: ['gone-tag'] })]
    store.activeId = 's1'
    concordance.filters = filtersOf(store.items[0]!.query!)
    await wrapper.vm.$nextTick()
    expect(find(wrapper, 'saved-filter-name').text()).toBe('Praha')
    expect(find(wrapper, 'saved-filter-status').text()).toMatch(/Filters saved$/)
    expect(find(wrapper, 'saved-filter-save').exists()).toBe(false)
    expect(find(wrapper, 'saved-filter-warning').exists()).toBe(true) // names a deleted tag

    await wrapper.setProps({ tags: [] }) // the collection's last tag was deleted: still warned
    expect(find(wrapper, 'saved-filter-warning').exists()).toBe(true)
    await wrapper.setProps({ definitionsReady: false }) // not loaded yet: no false warning
    expect(find(wrapper, 'saved-filter-warning').exists()).toBe(false)
    await wrapper.setProps({ tags: TAGS, definitionsReady: true })

    concordance.filters = filters({ text: 'Brno' })
    await wrapper.vm.$nextTick()
    expect(find(wrapper, 'saved-filter-status').text()).toBe('Unsaved changes')
    expect(find(wrapper, 'saved-filter-save').attributes('disabled')).toBeUndefined()
    expect(find(wrapper, 'saved-filter-discard').exists()).toBe(true)
    store.items = [saved('s1', 'Praha', { text: 'Praha' }, { canEdit: false })]
    await wrapper.vm.$nextTick()
    expect(find(wrapper, 'saved-filter-save').attributes('disabled')).toBeDefined() // only its creator and the owner
    wrapper.unmount()
  })
})

describe('saved filters menu', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('keeps an unreadable saved filter renamable and deletable, only not openable (#828 review)', async () => {
    const store = useSavedFiltersStore()
    store.items = [saved('s1', 'Old', {}, { unreadable: true, query: null, canEdit: true })]
    const wrapper = mount(SavedFiltersMenu, {
      props: { collectionId: 'col-1', people: [], me: 'u1' },
      global: { plugins: [[Quasar, {}]] },
      attachTo: document.body
    })
    store.load = vi.fn() as never
    await wrapper.find('[data-testid="saved-filters-menu"]').trigger('click')
    await flushPromises()
    const item = document.querySelector('[data-testid="saved-filters-item"]') as HTMLElement
    expect(item.textContent).toContain('Cannot be opened by this version')
    expect(item.getAttribute('aria-disabled')).not.toBe('true')
    for (const id of ['saved-filters-rename', 'saved-filters-delete']) {
      const button = item.querySelector(`[data-testid="${id}"]`) as HTMLButtonElement
      expect(button.disabled || button.getAttribute('aria-disabled') === 'true').toBe(false)
    }
    item.click()
    await flushPromises()
    expect(store.activeId).toBeNull() // not opened
    wrapper.unmount()
  })
})
