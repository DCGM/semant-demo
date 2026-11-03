import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { documentLink, returnLink } from 'src/features/documents/workspace/documentLink'
import { parseMode, shownMode, withMode } from 'src/features/documents/workspace/workspaceMode'
import { keepScrollOfKeptPages } from 'src/router/keptPages'

// The paired document workspace (#545): its views, the links to the public document view and
// back, and the scroll position of the pages kept alive while a document is shown.

describe('workspace views', () => {
  it('show the chosen view, text alone without scans, and one view on a narrow screen', () => {
    expect(shownMode('split', { hasScan: true, narrow: false })).toBe('split')
    expect(shownMode('scan', { hasScan: true, narrow: false })).toBe('scan')
    expect(shownMode('split', { hasScan: true, narrow: true })).toBe('text')
    expect(shownMode('scan', { hasScan: true, narrow: true })).toBe('scan')
    expect(shownMode('scan', { hasScan: false, narrow: false })).toBe('text')
    expect(shownMode('split', { hasScan: false, narrow: true })).toBe('text')
  })

  it('are read from and written to `?view=`, the default left out', () => {
    expect(parseMode('scan')).toBe('scan')
    expect(parseMode('both')).toBeNull()
    expect(parseMode(['scan'])).toBeNull()
    expect(withMode({ page: 'p1', view: 'scan' }, 'split')).toEqual({ page: 'p1' })
    expect(withMode({ page: 'p1' }, 'text')).toEqual({ page: 'p1', view: 'text' })
  })
})

describe('document links', () => {
  it('name a passage, or else a page, and where the reader came from', () => {
    expect(documentLink('d1', { chunkId: 'c1', start: 0, end: 4, pageId: 'p1', from: 'search' })).toEqual({
      name: 'document', params: { documentId: 'd1' }, query: { chunk: 'c1', start: '0', end: '4', from: 'search' }
    })
    expect(documentLink('d1', { pageId: 'p1' })).toEqual({ name: 'document', params: { documentId: 'd1' }, query: { page: 'p1' } })
    expect(documentLink('d1')).toEqual({ name: 'document', params: { documentId: 'd1' }, query: {} })
  })

  it('lead back to Search or Chat, and nowhere for another or no origin', () => {
    expect(returnLink('search')).toMatchObject({ to: { name: 'search' }, ariaLabel: 'Back to search results' })
    expect(returnLink('chat')).toMatchObject({ to: { name: 'rag' }, ariaLabel: 'Back to the conversation' })
    expect(returnLink('collections')).toBeNull()
    expect(returnLink(undefined)).toBeNull()
  })
})

describe('pages kept alive', () => {
  it('open at their last scroll position, other pages at the top; browser history wins', async () => {
    const Page = { render: () => null }
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { name: 'search', path: '/search', component: Page, meta: { keepAlive: true } },
        { name: 'document', path: '/documents/:documentId', component: Page },
        { name: 'about', path: '/about', component: Page }
      ]
    })
    let y = 0
    const scroll = keepScrollOfKeptPages(router, () => y)
    await router.push('/search')
    y = 640
    await router.push('/documents/d1')
    const route = (path: string) => router.resolve(path)
    expect(await scroll(route('/search'), route('/documents/d1'), null)).toEqual({ left: 0, top: 640 })
    expect(await scroll(route('/about'), route('/documents/d1'), null)).toEqual({ left: 0, top: 0 })
    expect(await scroll(route('/search'), route('/documents/d1'), { left: 0, top: 12 })).toEqual({ left: 0, top: 12 })
  })
})
