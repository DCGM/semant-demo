import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { Quasar } from 'quasar'

import type { DocumentChunk, SearchResultChunk } from 'src/generated/api'
import ChunkContextPanel from 'src/features/documents/ChunkContextPanel.vue'
import DocumentMetadataPanel from 'src/features/documents/DocumentMetadataPanel.vue'
import OriginalSourceLink from 'src/features/documents/OriginalSourceLink.vue'
import { originalSourceUrl } from 'src/features/documents/originalSource'
import SearchResultCard from 'src/features/search/SearchResultCard.vue'

// Links to the original digitized document in its digital library (#255).

const DOC = 'c83ccd83-c8c2-4f86-af83-44e509025f50'
const PAGE = '58ac2055-9cbf-4bf0-a317-3e19c5bf0759'
const VIEW = `https://www.digitalniknihovna.cz/mzk/view/uuid:${DOC}`

describe('originalSourceUrl', () => {
  it('opens the document, at a page when one is given', () => {
    expect(originalSourceUrl({ id: DOC, library: 'mzk' })).toBe(VIEW)
    expect(originalSourceUrl({ id: DOC, library: 'mzk' }, PAGE)).toBe(`${VIEW}?page=uuid:${PAGE}`)
  })

  it('uses each document\'s own library', () => {
    expect(originalSourceUrl({ id: DOC, library: 'nkp' })).toBe(`https://www.digitalniknihovna.cz/nkp/view/uuid:${DOC}`)
    expect(originalSourceUrl({ id: DOC, library: 'knav' }, PAGE))
      .toBe(`https://www.digitalniknihovna.cz/knav/view/uuid:${DOC}?page=uuid:${PAGE}`)
    expect(originalSourceUrl({ id: DOC, library: 'cuni_fsv' })).toBe(`https://www.digitalniknihovna.cz/cuni_fsv/view/uuid:${DOC}`)
    expect(originalSourceUrl({ id: DOC, library: ' MZK ' })).toBe(VIEW)
  })

  it('accepts Kramerius uuid: prefixes and normalizes case', () => {
    expect(originalSourceUrl({ id: `uuid:${DOC.toUpperCase()}`, library: 'mzk' }, `uuid:${PAGE}`))
      .toBe(`${VIEW}?page=uuid:${PAGE}`)
  })

  it.each([
    ['no document', null],
    ['no library', { id: DOC }],
    ['a null library', { id: DOC, library: null }],
    ['an empty library', { id: DOC, library: '' }],
    ['an unknown library', { id: DOC, library: 'ndk' }],
    ['a library with a path', { id: DOC, library: 'mzk/../evil' }],
    ['a URL as library', { id: DOC, library: 'https://evil.example' }],
    ['a non-UUID id', { id: 'doc-1', library: 'mzk' }],
    ['a UUID-like id with extra text', { id: `${DOC}/../x`, library: 'mzk' }],
    ['a URL as id', { id: 'https://www.digitalniknihovna.cz/mzk/view/uuid:x', library: 'mzk' }]
  ])('gives no link for %s', (_, document) => {
    expect(originalSourceUrl(document, PAGE)).toBeNull()
  })

  it.each([undefined, null, '', 'p1', `${PAGE}&x=1`, 'javascript:alert(1)'])(
    'drops a missing or malformed page (%s) and still opens the document', (page) => {
      expect(originalSourceUrl({ id: DOC, library: 'mzk' }, page)).toBe(VIEW)
    })
})

const mountWith = <T>(component: T, props: Record<string, unknown>) =>
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  mount(component as any, { props, global: { plugins: [[Quasar, {}]] } })

describe('OriginalSourceLink', () => {
  it('opens the original in a new tab without opener or referrer, with a clear label', () => {
    const link = mountWith(OriginalSourceLink, { document: { id: DOC, library: 'mzk' }, pageId: PAGE })
      .get('a[data-testid="original-source-link"]')
    expect(link.attributes('href')).toBe(`${VIEW}?page=uuid:${PAGE}`)
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toBe('noopener noreferrer')
    expect(link.text()).toContain('View in digital library')
    expect(link.attributes('aria-label')).toBe('View in digital library (MZK, opens in a new tab)')
  })

  it('renders nothing without a resolvable link', () => {
    const wrapper = mountWith(OriginalSourceLink, { document: { id: DOC } })
    expect(wrapper.find('a').exists()).toBe(false)
  })
})

const hit = (library: string | null, title: string | null = 'Rovnost') => ({
  id: 'chunk-1',
  title: 'Chunk',
  queryTitle: null,
  text: 'Passage',
  language: 'cs',
  fromPage: 3,
  toPage: 3,
  startPageId: PAGE,
  document: DOC,
  documentObject: { id: DOC, library, title }
}) as unknown as SearchResultChunk

describe('views linking to the original', () => {
  const link = (wrapper: ReturnType<typeof mountWith>) => wrapper.find('[data-testid="original-source-link"]')

  it('search result cards open the original at the passage\'s first page, next to the source title', () => {
    const card = mountWith(SearchResultCard, { chunk: hit('mzk'), number: 1, filters: [] })
    const source = card.get('.search-result__source')
    expect(source.text()).toContain('Rovnost')
    expect(link(card).attributes('href')).toBe(`${VIEW}?page=uuid:${PAGE}`)
    // The internal "View in document" action is unchanged and separate.
    expect(card.find('[data-testid="view-context"]').exists()).toBe(true)
  })

  it('search result cards without a library keep the source title and offer no link', () => {
    const card = mountWith(SearchResultCard, { chunk: hit(null), number: 1, filters: [] })
    expect(card.get('.search-result__source').text()).toContain('Rovnost')
    expect(link(card).exists()).toBe(false)
  })

  it('a search result without a title still offers the original', () => {
    const card = mountWith(SearchResultCard, { chunk: hit('nkp', null), number: 1, filters: [] })
    expect(card.get('.search-result__source').text()).not.toContain('Source:')
    expect(link(card).attributes('href')).toContain('/nkp/view/')
  })

  it('the context view opens the original at the matched passage\'s page', () => {
    const chunk = (n: number, page: string): DocumentChunk => ({
      id: `c${n}`, text: `Text ${n}`, startPageId: page, fromPage: n, toPage: n, document: DOC, order: n
    } as DocumentChunk)
    const otherPage = '00000000-0000-4000-8000-000000000001'
    const panel = mountWith(ChunkContextPanel, {
      targetChunkId: 'c2',
      document: { id: DOC, library: 'mzk', title: 'Rovnost' },
      chunks: [chunk(1, otherPage), chunk(2, PAGE)]
    })
    expect(link(panel).attributes('href')).toBe(`${VIEW}?page=uuid:${PAGE}`)
  })

  it('the context view keeps the matched page when extending trims the target, and forgets it for a new target', async () => {
    const chunk = (n: number, page: string): DocumentChunk => ({
      id: `c${n}`, text: `Text ${n}`, startPageId: page, fromPage: n, toPage: n, document: DOC, order: n
    } as DocumentChunk)
    const laterPage = '00000000-0000-4000-8000-000000000003'
    const newPage = '00000000-0000-4000-8000-000000000009'
    const document = { id: DOC, library: 'mzk', title: 'Rovnost' }
    const panel = mountWith(ChunkContextPanel, { targetChunkId: 'c2', document, chunks: [chunk(1, PAGE), chunk(2, PAGE)] })

    // Extending later text keeps at most a bounded window: the target chunk is dropped.
    await panel.setProps({ chunks: [chunk(3, laterPage), chunk(4, laterPage)] })
    expect(link(panel).attributes('href')).toBe(`${VIEW}?page=uuid:${PAGE}`)

    // Another target: no page until it is loaded, then its own.
    await panel.setProps({ targetChunkId: 'c9', chunks: [] })
    expect(link(panel).attributes('href')).toBe(VIEW)
    await panel.setProps({ chunks: [chunk(9, newPage)] })
    expect(link(panel).attributes('href')).toBe(`${VIEW}?page=uuid:${newPage}`)
  })

  it('the document metadata panel links to the document, or says the original is not available', () => {
    const linked = mountWith(DocumentMetadataPanel, { document: { id: DOC, library: 'mzk' } })
    expect(link(linked).attributes('href')).toBe(VIEW)

    const unlinked = mountWith(DocumentMetadataPanel, { document: { id: DOC, library: 'unknown' } })
    expect(link(unlinked).exists()).toBe(false)
    expect(unlinked.text()).toContain('Not available')
  })
})
