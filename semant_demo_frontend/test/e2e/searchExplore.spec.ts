import { expect, test, type Page, type Request } from '@playwright/test'

import { fixture, isPassageSearch, useViewport } from './support'

// The Search page evolving into Explore Results (#605, #606, #607): draft and applied criteria, the
// applied search in the URL (reload, Back/Forward, shared links), Passages and Documents loaded
// page by page with their coverage, the results mode switch, late answers dropped, and the
// reader's way back to the search.

const input = (page: Page) => page.getByRole('combobox', { name: 'Search query' })
const chip = (page: Page, text: string) => page.locator('.active-filter-chip', { hasText: text })
const nextSearch = (page: Page): Promise<Request> => page.waitForRequest((r) => isPassageSearch(r.url(), r.method()))
const isDocumentSearch = (r: Request) => new URL(r.url()).pathname.endsWith('/api/search/documents') && r.method() === 'POST'
const nextDocuments = (page: Page): Promise<Request> => page.waitForRequest(isDocumentSearch)
const documentTitles = (page: Page) => page.getByTestId('document-result-open')
const modeButton = (page: Page, mode: 'documents' | 'passages') => page.getByTestId(`results-mode-${mode}`)
const hash = (page: Page) => decodeURIComponent(new URL(page.url()).hash).replace(/\+/g, ' ')

async function openSearch (page: Page, path = '/#/search') {
  await page.goto(path)
}

/** Runs the query in the field (Enter) and waits for its first result; returns its request. */
async function searchFor (page: Page, query: string): Promise<Request> {
  await input(page).fill(query)
  const request = nextSearch(page)
  await input(page).press('Enter')
  const sent = await request
  await expect(page.locator('#result-1')).toBeVisible()
  return sent
}

async function chooseLanguage (page: Page, label: string) {
  await page.getByRole('button', { name: 'Search filters' }).click()
  await page.getByLabel('Language', { exact: true }).click()
  await page.getByRole('option', { name: label, exact: true }).click()
  await page.keyboard.press('Escape') // closes the options menu
  await page.getByRole('button', { name: 'Search filters' }).click()
}

for (const viewport of ['wide', 'phone'] as const) {
  test(`applied criteria live in the URL: reload, Back and Forward restore them (${viewport})`, async ({ page }) => {
    await useViewport(page, viewport)
    await openSearch(page)
    await searchFor(page, 'Lhota')
    expect(hash(page)).toBe('#/search?q=Lhota')
    const firstText = await page.locator('#result-1 .search-result__text').textContent()

    // A filter is a draft until applied: the results and chips stay those of the search.
    await chooseLanguage(page, 'Czech')
    await expect(page.getByTestId('search-pending')).toBeVisible()
    await expect(chip(page, 'Language: Czech')).toHaveCount(0)
    await expect(page.locator('#result-1 .search-result__text')).toHaveText(firstText ?? '')

    const filtered = nextSearch(page)
    await input(page).press('Enter')
    expect((await filtered).postDataJSON().criteria).toMatchObject({ text_query: 'Lhota', chunk_filters: { languages: ['ces'] } })
    await expect(chip(page, 'Language: Czech')).toBeVisible()
    await expect(page.getByTestId('search-pending')).toHaveCount(0)
    expect(hash(page)).toBe('#/search?q=Lhota&chunk_languages=ces')

    // Another search; removing an applied chip searches again without it at once.
    await searchFor(page, 'Brno')
    expect(hash(page)).toBe('#/search?q=Brno&chunk_languages=ces')
    const removed = nextSearch(page)
    await chip(page, 'Language: Czech').locator('.q-chip__icon--remove').click()
    expect((await removed).postDataJSON().criteria.chunk_filters.languages).toEqual([])
    expect(hash(page)).toBe('#/search?q=Brno')

    // Back and Forward restore each applied search, in the form and in the results.
    let restored = nextSearch(page)
    await page.goBack()
    expect((await restored).postDataJSON().criteria).toMatchObject({ text_query: 'Brno', chunk_filters: { languages: ['ces'] } })
    await expect(chip(page, 'Language: Czech')).toBeVisible()
    restored = nextSearch(page)
    await page.goBack()
    expect((await restored).postDataJSON().criteria).toMatchObject({ text_query: 'Lhota', chunk_filters: { languages: ['ces'] } })
    await expect(input(page)).toHaveValue('Lhota')
    restored = nextSearch(page)
    await page.goForward()
    expect((await restored).postDataJSON().criteria.text_query).toBe('Brno')
    await expect(input(page)).toHaveValue('Brno')
    await expect(chip(page, 'Language: Czech')).toBeVisible()

    // A reload (or a shared link) runs the same search.
    const reloaded = nextSearch(page)
    await page.reload()
    expect((await reloaded).postDataJSON().criteria).toMatchObject({ text_query: 'Brno', chunk_filters: { languages: ['ces'] } })
    await expect(input(page)).toHaveValue('Brno')
    await expect(chip(page, 'Language: Czech')).toBeVisible()
    await expect(page.locator('#result-1')).toBeVisible()
  })
}

test('Discard changes puts the applied search back into the form', async ({ page }) => {
  await openSearch(page)
  await searchFor(page, 'Lhota')
  await input(page).fill('Brno')
  await expect(page.getByTestId('search-pending')).toBeVisible()
  await page.getByRole('button', { name: 'Discard changes' }).click()
  await expect(input(page)).toHaveValue('Lhota')
  await expect(page.getByTestId('search-pending')).toHaveCount(0)
})

test('a link with values that are not valid or not offered searches without them and says so', async ({ page }) => {
  const sent = nextSearch(page)
  await openSearch(page, '/#/search?q=Lhota&year_min=soon&chunk_classifications=complexity:trivial')
  const criteria = (await sent).postDataJSON().criteria
  expect(criteria).toMatchObject({ text_query: 'Lhota', document_filters: { year_min: null }, chunk_filters: { classifications: {} } })
  await expect(page.getByText('Left out of the search because they are not valid: Publication year from: soon')).toBeVisible()
  await expect(page.getByText('Left out of the search because they are not available: Complexity: trivial')).toBeVisible()
  await expect(page.locator('#result-1')).toBeVisible()
  await expect.poll(() => hash(page)).toBe('#/search?q=Lhota')
})

test('Load more reads the rest of the one ranking and says what the results cover', async ({ page }) => {
  // A first page of three, so Load more has the other four ranked passages to read (#611).
  let rankedIds: string[] = []
  const reads: string[][] = []
  await page.route('**/api/search/passages', async (route) => {
    const response = await route.fetch({ postData: JSON.stringify({ ...route.request().postDataJSON(), limit: 3 }) })
    rankedIds = (await response.json()).ranked_ids
    await route.fulfill({ response })
  })
  let searches = 0
  page.on('request', (r) => {
    if (isPassageSearch(r.url(), r.method())) searches++
    if (r.url().endsWith('/api/search/passages/read')) reads.push(r.postDataJSON().ids)
  })
  await openSearch(page)
  await searchFor(page, 'Lhota')
  const coverage = page.getByTestId('search-coverage')
  await expect(page.locator('.search-result')).toHaveCount(3)
  await expect(coverage).toContainText('7 matching passages (3 shown).') // the whole ranking is known at once

  const more = page.getByTestId('search-load-more')
  await more.click()
  await expect(page.locator('.search-result')).toHaveCount(7) // every fixture chunk, once
  await expect(more).toHaveCount(0)
  await expect(coverage).toContainText('All 7 matching passages.')
  expect(searches).toBe(1) // ranked once; Load more read the next ranked ids
  expect(reads).toEqual([rankedIds.slice(3)])
  const ids = await page.locator('.search-result').evaluateAll(cards => cards.map(c => c.id))
  expect(new Set(ids).size).toBe(7)
})

test('a late answer of an earlier search never replaces the newer results', async ({ page }) => {
  let release: () => void = () => undefined
  const held = new Promise<void>((resolve) => { release = resolve })
  let settled: () => void = () => undefined
  const heldDone = new Promise<void>((resolve) => { settled = resolve })
  await page.route('**/api/search/passages', async (route) => {
    const isHeld = route.request().postDataJSON().criteria.text_query === 'Lhota'
    if (isHeld) await held
    // The page may have aborted the held request meanwhile; its answer is then refused.
    await route.continue().catch(() => undefined)
    if (isHeld) settled()
  })
  await openSearch(page)
  await input(page).fill('Lhota')
  await input(page).press('Enter')
  await expect(page.getByTestId('search-loading')).toBeVisible()

  const brno = fixture.chunk('letters_1').text
  await searchFor(page, brno)
  const shown = await page.locator('#result-1 .search-result__text').textContent()
  release()
  await heldDone // the held search was answered (or refused, aborted); either way it is dropped
  await expect(page.locator('#result-1 .search-result__text')).toHaveText(shown ?? '')
  await expect(input(page)).toHaveValue(brno)
  expect(new URLSearchParams(hash(page).split('?')[1]).get('q')).toBe(brno)
})

test('a passage opened in the reader leads back to the same search, not an empty one', async ({ page }) => {
  await openSearch(page)
  await searchFor(page, 'Lhota')
  await chooseLanguage(page, 'Czech')
  await input(page).press('Enter')
  await expect(chip(page, 'Language: Czech')).toBeVisible()
  const searchUrl = hash(page)

  await page.locator('#result-1').getByRole('button', { name: /in its document$/ }).click()
  await page.getByTestId('chunk-context-open').click()
  await expect(page).toHaveURL(/#\/documents\/.*from=search/)

  let searches = 0
  page.on('request', (r) => { if (isPassageSearch(r.url(), r.method())) searches++ })
  await page.getByRole('link', { name: 'Back to search results' }).click()
  await expect(page.locator('#result-1')).toBeVisible()
  expect(hash(page)).toBe(searchUrl)
  await expect(chip(page, 'Language: Czech')).toBeVisible()
  expect(searches).toBe(0) // the kept results, not a new search
})

/// ///////////////////////////
// Documents results (#606) //
/// ///////////////////////////

const CHRONICLE = 'Kronika obce Lhota' // 1851
const LETTERS = 'Dopisy z Prahy' // 1902
const GAZETTE = 'Pražský věstník' // no year
const ORDER = 'Sorted by publication year, oldest first; documents without a year last.'
const RANKED_ORDER = 'Matches in the title, author or publisher first, then by the best-matching passage.'
const isDocumentRead = (r: Request) => new URL(r.url()).pathname.endsWith('/api/search/documents/read') && r.method() === 'POST'

for (const viewport of ['wide', 'phone'] as const) {
  test(`filters alone list Documents; the mode switch keeps the criteria in the URL and history (${viewport})`, async ({ page }) => {
    await useViewport(page, viewport)
    await openSearch(page)
    await chooseLanguage(page, 'Czech')
    const listed = nextDocuments(page)
    await input(page).press('Enter')
    // Per dimension, from the documents' chunk-value summaries: every fixture chunk is Czech.
    expect((await listed).postDataJSON()).toMatchObject({ criteria: { text_query: null, chunk_filters: { languages: ['ces'] } }, limit: 20, offset: 0 })
    await expect(documentTitles(page)).toHaveText([`1. ${CHRONICLE}`, `2. ${LETTERS}`, `3. ${GAZETTE}`])
    await expect(page.getByTestId('document-result-year').nth(2)).toContainText('Year unknown')
    await expect(page.getByTestId('search-coverage')).toHaveText(`All 3 matching documents. ${ORDER}`)
    await expect(modeButton(page, 'documents')).toHaveAttribute('aria-pressed', 'true')
    expect(hash(page)).toBe('#/search?chunk_languages=ces')

    // Passages need a text query: the same criteria, a state that says so, a history entry.
    await modeButton(page, 'passages').click()
    await expect(page.getByTestId('search-needs-query')).toBeVisible()
    await expect(chip(page, 'Language: Czech')).toBeVisible()
    expect(hash(page)).toBe('#/search?chunk_languages=ces&mode=passages')
    const back = nextDocuments(page)
    await page.goBack()
    await back
    await expect(documentTitles(page)).toHaveCount(3)
    expect(hash(page)).toBe('#/search?chunk_languages=ces')

    // A text query searches Passages by default; Documents rank the same criteria (#607): the
    // title match first, then the other documents by their best passage.
    await searchFor(page, 'Lhota')
    expect(hash(page)).toBe('#/search?q=Lhota&chunk_languages=ces')
    await expect(modeButton(page, 'passages')).toHaveAttribute('aria-pressed', 'true')
    let ranked = nextDocuments(page)
    await modeButton(page, 'documents').click()
    expect((await ranked).postDataJSON()).toMatchObject({ criteria: { text_query: 'Lhota', chunk_filters: { languages: ['ces'] } }, type: 'hybrid', offset: 0 })
    await expect(documentTitles(page)).toHaveCount(3)
    await expect(documentTitles(page).first()).toHaveText(`1. ${CHRONICLE}`)
    await expect(page.getByTestId('document-result-match').first()).toHaveText(/Matches the title, author or publisher/)
    await expect(page.getByTestId('search-coverage')).toHaveText(`All 3 matching documents. ${RANKED_ORDER}`)
    expect(hash(page)).toBe('#/search?q=Lhota&chunk_languages=ces&mode=documents')
    ranked = nextDocuments(page)
    await page.reload()
    await ranked
    await expect(documentTitles(page).first()).toHaveText(`1. ${CHRONICLE}`)
    await expect(chip(page, 'Language: Czech')).toBeVisible()

    // Another text query stays in Documents.
    await input(page).fill('Prahy')
    ranked = nextDocuments(page)
    await input(page).press('Enter')
    expect((await ranked).postDataJSON().criteria.text_query).toBe('Prahy')
    await expect(documentTitles(page).first()).toHaveText(`1. ${LETTERS}`)
    expect(hash(page)).toBe('#/search?q=Prahy&chunk_languages=ces&mode=documents')
  })
}

test('an empty search lists every document, and Load more reads the next page in the same order', async ({ page }) => {
  // A first page of one, so Load more has the two other documents to read.
  await page.route('**/api/search/documents', async (route) => {
    const body = route.request().postDataJSON()
    const response = await route.fetch({ postData: JSON.stringify(body.offset === 0 ? { ...body, limit: 1 } : body) })
    await route.fulfill({ response })
  })
  const pages: { offset: number, limit: number }[] = []
  page.on('request', (r) => { if (isDocumentSearch(r)) pages.push(r.postDataJSON()) })
  await openSearch(page)
  await input(page).press('Enter')
  await expect(documentTitles(page)).toHaveText([`1. ${CHRONICLE}`])
  expect(hash(page)).toBe('#/search?mode=documents') // not the page as first opened
  await expect(page.getByTestId('search-coverage')).toHaveText(`3 matching documents (1 shown). ${ORDER}`)

  await page.getByTestId('search-load-more').click()
  await expect(documentTitles(page)).toHaveText([`1. ${CHRONICLE}`, `2. ${LETTERS}`, `3. ${GAZETTE}`])
  await expect(page.getByTestId('search-load-more')).toHaveCount(0)
  await expect(page.getByTestId('search-coverage')).toHaveText(`All 3 matching documents. ${ORDER}`)
  expect(pages.map(p => [p.offset, p.limit])).toEqual([[0, 20], [1, 100]])
})

test('a document opened from the Documents results leads back to the same results', async ({ page }) => {
  await openSearch(page, '/#/search?year_max=1900')
  await expect(documentTitles(page)).toHaveText([`1. ${CHRONICLE}`])
  const searchUrl = hash(page)

  await documentTitles(page).first().click()
  await expect(page).toHaveURL(new RegExp(`#/documents/${fixture.document('chronicle').id}\\?from=search`))
  let searches = 0
  page.on('request', (r) => { if (isDocumentSearch(r)) searches++ })
  await page.getByRole('link', { name: 'Back to search results' }).click()
  await expect(documentTitles(page)).toHaveText([`1. ${CHRONICLE}`])
  expect(hash(page)).toBe(searchUrl)
  expect(searches).toBe(0) // the kept results, not a new search
})

test('documents ranked by a text query load more by their ranking, and open at their best passage', async ({ page }) => {
  // A first page of one, so Load more reads the two other ranked documents by id (#607).
  await page.route('**/api/search/documents', async (route) => {
    const response = await route.fetch({ postData: JSON.stringify({ ...route.request().postDataJSON(), limit: 1 }) })
    await route.fulfill({ response })
  })
  let searches = 0
  page.on('request', (r) => { if (isDocumentSearch(r)) searches++ })
  await openSearch(page, '/#/search?q=Lhota&mode=documents')
  await expect(documentTitles(page)).toHaveText([`1. ${CHRONICLE}`])
  await expect(page.getByTestId('search-coverage')).toHaveText(`3 matching documents (1 shown). ${RANKED_ORDER}`)

  const read = page.waitForRequest(isDocumentRead)
  await page.getByTestId('search-load-more').click()
  const entries = (await read).postDataJSON().ranked
  expect(entries).toHaveLength(2)
  await expect(documentTitles(page)).toHaveCount(3)
  await expect(page.getByTestId('search-load-more')).toHaveCount(0)
  await expect(page.getByTestId('search-coverage')).toHaveText(`All 3 matching documents. ${RANKED_ORDER}`)
  expect(searches).toBe(1) // one ranking

  // The best passage opens the reader at it; the way back finds the same results.
  const second = page.locator('#document-2')
  const target = entries[0]
  await second.getByTestId('document-result-evidence').click()
  await expect(page).toHaveURL(new RegExp(`#/documents/${target.id}\\?chunk=${target.chunk_id}&from=search`))
  await page.getByRole('link', { name: 'Back to search results' }).click()
  await expect(documentTitles(page)).toHaveCount(3)
  expect(searches).toBe(1)
})

test('a filter the corpus database cannot answer is reported, not shown as no documents', async ({ page }) => {
  const detail = 'Documents cannot be filtered by chunk values (chunk_language): this corpus database has no chunk-value summaries of its documents.'
  await page.route('**/api/search/documents', (route) => route.fulfill({ status: 422, json: { detail } }))
  await openSearch(page, '/#/search?chunk_languages=ces')
  await expect(page.getByTestId('search-error')).toContainText(detail)
  await expect(page.getByTestId('search-empty')).toHaveCount(0)
})

test('documents that match no filter say so', async ({ page }) => {
  await openSearch(page, '/#/search?chunk_classifications=communicative_mode:narration&year_min=1900')
  await expect(page.getByTestId('search-empty')).toContainText('No documents match these filters.')
  await expect(page.getByTestId('search-coverage')).toHaveCount(0)
})
