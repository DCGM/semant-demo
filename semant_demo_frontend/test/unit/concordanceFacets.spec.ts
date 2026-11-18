import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { QSelect, Quasar } from 'quasar'

import { RetrievalMode, type AnnotationFacets } from 'src/generated/api'
import ConcordanceToolbar from 'src/features/annotations/concordance/ConcordanceToolbar.vue'
import { MAX_FACET_ATTRIBUTES, defaultFilters, facetsRequest, useConcordanceStore, withMode } from 'src/features/annotations/concordance/concordanceStore'

// Facet counts of the annotation query (#667): the request carries the query and every menu's
// facet, a failed read only leaves the menus without counts, and the menus show the counts.

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

const facets = (extra: Partial<AnnotationFacets> = {}): AnnotationFacets => ({
  population: 'filtered',
  selfExclusion: true,
  facets: [
    { facet: 'tag', values: [{ value: 't1', count: 5 }], missing: 0, total: 5 },
    { facet: 'type', values: [{ value: 'pos', count: 4 }, { value: 'auto', count: 1 }], missing: 0, total: 5 },
    { facet: 'year', values: [{ value: '1850', count: 2 }, { value: '1912', count: 3 }], missing: 1, total: 6 },
    { facet: 'attribute:a1', values: [{ value: 'v1', count: 3, inapplicable: 1 }], missing: 2, total: 5 }
  ],
  ...extra
} as AnnotationFacets)

describe('facets of the concordance store', () => {
  const originalFetch = globalThis.fetch
  let requests: { path: string, body: Record<string, unknown> | undefined }[]
  let facetStatus: number

  beforeEach(() => {
    setActivePinia(createPinia())
    requests = []
    facetStatus = 200
    globalThis.fetch = vi.fn(async (input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => {
      const path = new URL(String(input)).pathname
      requests.push({ path, body: typeof init?.body === 'string' ? JSON.parse(init.body) : undefined })
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
      if (path.endsWith('/facets')) return facetStatus === 200 ? json(facets()) : json({ detail: 'x' }, facetStatus)
      if (path.endsWith('/documents')) return json([])
      if (path.endsWith('/ids')) return json({ ids: [], versions: {} })
      return json({ rows: [], total: 0, offset: 0, limit: 50 })
    }) as typeof fetch
  })
  afterEach(() => { globalThis.fetch = originalFetch })

  const facetCalls = () => requests.filter(r => r.path.endsWith('/facets'))

  it('asks for the choices of every menu with the query, again when the query changes', async () => {
    const store = useConcordanceStore()
    store.facetAttributeIds = ['a1']
    await store.open('col-1')
    await flush()
    expect(facetCalls()).toHaveLength(1)
    expect(facetCalls()[0].body).toMatchObject({
      types: ['pos', 'auto'], facets: ['tag', 'type', 'document', 'year', 'library', 'language', 'attribute:a1']
    })
    expect(store.facets?.population).toBe('filtered')

    await store.setFilters({ tagIds: ['t1'], text: 'praha' })
    await flush()
    expect(facetCalls()).toHaveLength(2)
    expect(facetCalls()[1].body).toMatchObject({ tag_ids: ['t1'], q: 'praha' })

    await store.setFilters({ descending: true }) // the order does not change any count
    await flush()
    expect(facetCalls()).toHaveLength(2)
  })

  it('counts a ranked query as its top k', () => {
    const request = facetsRequest(withMode({ ...defaultFilters(), similarity: 'hejtman' }), [])
    expect(request.ranking).toMatchObject({ mode: RetrievalMode.hybrid, k: 100 })
    expect(request.rankingQuery).toBe('hejtman')
  })

  it('asks for at most 90 attribute facets, so a request never exceeds the 100 the API takes', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const ids = Array.from({ length: 120 }, (_, i) => `a${i}`)
    const facetNames = facetsRequest(defaultFilters(), ids).facets
    expect(facetNames.filter(f => f.startsWith('attribute:'))).toHaveLength(MAX_FACET_ATTRIBUTES)
    expect(facetNames).toHaveLength(6 + 90)
    expect(facetsRequest(defaultFilters(), ids.slice(0, 3)).facets).toHaveLength(9)
  })

  it('shows the list without counts when reading them failed', async () => {
    facetStatus = 503
    const store = useConcordanceStore()
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    await store.open('col-1')
    await flush()
    expect(store.facets).toBeNull()
    expect(store.error).toBeNull()
  })
})

describe('counts in the filter menus', () => {
  const mountToolbar = (props: Record<string, unknown>) => mount(ConcordanceToolbar, {
    props: { filters: defaultFilters(), tags: [{ id: 't1', name: 'Place', color: '#f00' }, { id: 't2', name: 'Person', color: '#0f0' }], documents: [], ...props },
    global: { plugins: [Quasar] }
  } as never)

  it('shows the counts of the statuses and tags, 0 for a choice nothing matches', () => {
    const toolbar = mountToolbar({ facets: facets() })
    expect(toolbar.find('[data-testid="concordance-status-count-pos"]').text()).toBe('4')
    expect(toolbar.find('[data-testid="concordance-status-count-auto"]').text()).toBe('1')
    expect(toolbar.find('[data-testid="concordance-status-count-neg"]').text()).toBe('0')
    const tags = toolbar.findAllComponents(QSelect).find(s => s.props('label') === 'Tags')!
    expect((tags.props('options') as { count: number }[]).map(o => o.count)).toEqual([5, 0])
  })

  it('says in the count itself that a ranked query counts its top k', async () => {
    const toolbar = mountToolbar({ facets: facets() })
    expect(toolbar.find('[data-testid="concordance-status-count-pos"]').text()).toBe('4')
    await toolbar.setProps({ facets: facets({ population: 'top_k', selfExclusion: false, k: 100 } as never) })
    const count = toolbar.find('[data-testid="concordance-status-count-pos"]')
    expect(count.text()).toBe('4 in top 100')
    expect(count.classes()).toContain('concordance-toolbar__count--ranked')
    const tags = toolbar.findAllComponents(QSelect).find(s => s.props('label') === 'Tags')!
    expect(tags.props('popupContentStyle')).toBe('min-width: 320px')
  })

  it('counts the attribute values, marks the ones no longer applying and counts the unassigned', () => {
    const attribute = {
      id: 'a1',
      name: 'Kind',
      cardinality: 'single',
      allTags: true,
      tagIds: [],
      retired: false,
      revision: 1,
      values: [{ id: 'v1', label: 'Town', retired: false, kind: 'value' }, { id: 'v2', label: 'Village', retired: false, kind: 'value' }]
    }
    const toolbar = mountToolbar({ facets: facets(), attributes: [attribute] })
    const select = toolbar.findAllComponents(QSelect).find(s => s.props('label') === 'Attributes')!
    const options = select.props('options') as { value: string, count: number, inapplicable: number }[]
    expect(options.map(o => [o.value, o.count, o.inapplicable])).toEqual([['v:a1:v1', 3, 1], ['v:a1:v2', 0, 0], ['u:a1', 2, 0]])
  })

  it('shows no count for a document a truncated document facet left out, instead of an overstated one', () => {
    const documents = [
      { id: 'd1', title: 'Kronika', year: 1850, count: 9, available: true },
      { id: 'd2', title: 'Dopisy', year: 1900, count: 7, available: true }
    ]
    const named = (truncated: boolean) => facets({
      facets: [{ facet: 'document', values: [{ value: 'd1', count: 2 }], missing: 0, total: 2, distinct: 600, truncated }]
    } as never)
    const labels = (toolbar: ReturnType<typeof mountToolbar>) => (toolbar.findAllComponents(QSelect)
      .find(s => s.props('label') === 'Sources')!.props('options') as { label: string }[]).map(o => o.label)
    expect(labels(mountToolbar({ facets: named(true), documents }))).toEqual(['Kronika, 1850 (2)', 'Dopisy, 1900'])
    expect(labels(mountToolbar({ facets: named(false), documents }))).toEqual(['Kronika, 1850 (2)', 'Dopisy, 1900 (0)'])
  })

  it('hints the years with annotations', () => {
    const toolbar = mountToolbar({ facets: facets() })
    expect(toolbar.find('[data-testid="concordance-year-hint"]').text()).toBe('Annotations from 1850–1912; 1 without a year')
  })
})
