import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { Quasar } from 'quasar'

import type { DefaultApi, Document, DocumentHit, SearchResultChunk } from 'src/generated/api'
import DocumentRightsBadge from 'src/features/documents/DocumentRightsBadge.vue'
import { addRestrictedWarning, documentRights, nonPublicDocuments } from 'src/features/documents/documentRights'
import { documentLink } from 'src/features/documents/workspace/documentLink'
import { readPageChunks } from 'src/features/documents/correspondence/pageChunks'
import SearchResultCard from 'src/features/search/SearchResultCard.vue'
import DocumentResultCard from 'src/features/search/DocumentResultCard.vue'

// The source rights of corpus documents (#279): public documents carry no label; restricted
// (`public` false) and unknown (no value) ones are labelled where a collection shows them, and
// links and reads from a collection keep it.

const global = { plugins: [[Quasar, {}]] as never[], stubs: { RouterLink: { template: '<a><slot /></a>' } } }

describe('documentRights', () => {
  it('tells public, restricted and unknown documents apart', () => {
    expect([true, false, null, undefined].map(documentRights)).toEqual(['public', 'restricted', 'unknown', 'unknown'])
  })
})

describe('DocumentRightsBadge', () => {
  it.each([
    [true, null],
    [false, 'Restricted'],
    [null, 'Access unknown'],
    [undefined, 'Access unknown']
  ])('labels public=%s as %s', (value, label) => {
    const badge = mount(DocumentRightsBadge, { props: { value }, global })

    if (label === null) expect(badge.find('[data-testid="document-rights"]').exists()).toBe(false)
    else expect(badge.find('[data-testid="document-rights-label"]').text()).toBe(label)
  })
})

describe('result cards', () => {
  const documentObject = (rights: boolean | undefined): Document => ({ id: 'doc-1', title: 'Dopisy z Prahy', _public: rights })
  const chunk = (rights: boolean | undefined) => ({
    id: 'chunk-1',
    text: 'Milá Marie',
    fromPage: 1,
    toPage: 1,
    startPageId: 'p',
    document: 'doc-1',
    documentObject: documentObject(rights)
  }) as unknown as SearchResultChunk

  it('labels the passages of a restricted or unknown document, not of a public one', () => {
    const rights = (value: boolean | undefined) => mount(SearchResultCard, {
      props: { chunk: chunk(value), number: 1, filters: [] }, global
    }).find('[data-testid="document-rights-label"]')

    expect(rights(true).exists()).toBe(false)
    expect(rights(false).text()).toBe('Restricted')
    expect(rights(undefined).text()).toBe('Access unknown')
  })

  it('labels a restricted document result', () => {
    const hit = { document: documentObject(false) } as DocumentHit
    const card = mount(DocumentResultCard, { props: { hit, number: 1, collectionId: 'col-1' }, global })

    expect(card.find('[data-testid="document-rights-label"]').text()).toBe('Restricted')
  })
})

describe('links and reads through a collection', () => {
  it('keeps the collection in the link to the document view', () => {
    expect(documentLink('doc-1', { chunkId: 'c1', from: 'search', collectionId: 'col-1' })).toEqual({
      name: 'document', params: { documentId: 'doc-1' }, query: { chunk: 'c1', from: 'search', collection: 'col-1' }
    })
    expect(documentLink('doc-1', { chunkId: 'c1' })).toEqual({ name: 'document', params: { documentId: 'doc-1' }, query: { chunk: 'c1' } })
  })

  it('names the collection in the reads of a page', async () => {
    const byPage = vi.fn().mockResolvedValue({ page: 0, chunks: [], hasMore: false })
    const api = { readDocumentPageChunksApiDocumentsDocumentIdChunksByPageGet: byPage } as unknown as DefaultApi

    await readPageChunks(api, 'doc-1', 0, 'col-1')
    await readPageChunks(api, 'doc-1', 0)

    expect(byPage.mock.calls.map(([request]) => request.collectionId)).toEqual(['col-1', null])
  })
})

describe('adding documents that are not public (#789)', () => {
  it('names each restricted or unknown document once, never a public one', () => {
    const docs = [{ id: 'a', _public: false }, { id: 'b', _public: true }, { id: 'a', _public: false }, { id: 'c' }]
    expect(nonPublicDocuments(docs).map(d => d.id)).toEqual(['a', 'c'])
  })

  it('explains the lasting, independent route the add creates', () => {
    const one = addRestrictedWarning(['Dopisy z Prahy'], 'Noviny')
    expect(one).toContain('This document is not public: “Dopisy z Prahy”')
    expect(one).toContain('“Noviny”')
    expect(one).toContain('also after the collection you found it in stops being shared with you')
    expect(one).toContain('No copy is made')
    expect(addRestrictedWarning(['1', '2', '3', '4', '5', '6', '7'], 'X')).toContain('These 7 documents are not public: “1”, “2”, “3”, “4”, “5” and 2 more')
  })
})
