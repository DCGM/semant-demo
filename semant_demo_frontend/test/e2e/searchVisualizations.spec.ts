import { expect, test, type Page, type Request } from '@playwright/test'

import { closePhoneNavigation, ensureLoggedIn, fixture, isPassageSearch, logOut, useViewport } from './support'

// Explore Visualizations (#618, #620): a Results | Visualizations switch on the Search page over the
// same applied criteria and results mode, in the URL and history. Without a text query the charts
// count every document the filters match (the Analytics distributions, with the same document and
// per-dimension chunk filters as Documents); with one, exactly the results its search ranked
// (`POST /api/analytics/results/distributions`), whose categories can be inspected in Results
// without searching again. The fixture corpus has three documents, all `ces`, no library:
// chronicle 1851 (3 passages), letters 1902 (2) and gazette without a year (2); "Lhota" ranks all
// seven passages.

const input = (page: Page) => page.getByRole('combobox', { name: 'Search query' })
const chip = (page: Page, text: string) => page.locator('.active-filter-chip', { hasText: text })
const hash = (page: Page) => decodeURIComponent(new URL(page.url()).hash).replace(/\+/g, ' ')
const isDocumentSearch = (r: Request) => new URL(r.url()).pathname.endsWith('/api/search/documents') && r.method() === 'POST'
const isDistributions = (r: Request) => new URL(r.url()).pathname.endsWith('/api/analytics/corpus/distributions') && r.method() === 'POST'
const isRankedCount = (r: Request) => new URL(r.url()).pathname.endsWith('/api/analytics/results/distributions') && r.method() === 'POST'
const isRead = (r: Request) => /\/api\/search\/(documents|passages)\/read$/.test(new URL(r.url()).pathname) && r.method() === 'POST'
const documentTitles = (page: Page) => page.getByTestId('document-result-open')
const viewTab = (page: Page, view: 'results' | 'visualizations') => page.getByTestId(`view-${view}`)

/** Counts the requests of each kind from now on. */
function countRequests (page: Page) {
  const counts = { documents: 0, passages: 0, distributions: 0, ranked: 0, reads: 0 }
  page.on('request', (r) => {
    if (isDocumentSearch(r)) counts.documents++
    else if (isPassageSearch(r.url(), r.method())) counts.passages++
    else if (isDistributions(r)) counts.distributions++
    else if (isRankedCount(r)) counts.ranked++
    else if (isRead(r)) counts.reads++
  })
  return counts
}

async function openSearch (page: Page, path: string) {
  await page.goto(path)
  await closePhoneNavigation(page)
}

for (const viewport of ['wide', 'phone'] as const) {
  test(`Results and Visualizations share the applied criteria, URL and history (${viewport})`, async ({ page }) => {
    await useViewport(page, viewport)
    const counts = countRequests(page)
    await openSearch(page, '/#/search?year_max=1900&chunk_languages=ces')
    await expect(documentTitles(page)).toHaveText(['1. Kronika obce Lhota'])
    await expect(page.getByTestId('search-coverage')).toContainText('All 1 matching document.')

    // The charts count the documents of the same document and per-dimension chunk filters.
    const counted = page.waitForRequest(isDistributions)
    await viewTab(page, 'visualizations').click()
    expect((await counted).postDataJSON()).toEqual({
      filters: { year_min: null, year_max: 1900, title_contains: [], libraries: [], languages: [] },
      chunk_filters: { languages: ['ces'], classifications: {} }
    })
    await expect(page.getByTestId('charts-total')).toHaveText('1')
    await expect(page.getByTestId('charts-scope')).toContainText('1 document matches the applied filters.')
    await expect(page.getByTestId('charts-scope')).toContainText('different filters may be met by different passages')
    await expect(page.getByTestId('corpus-years')).toContainText('1 of 1 documents (100 %) have a publication year')
    await expect(chip(page, 'Language: Czech')).toBeVisible()
    expect(hash(page)).toBe('#/search?year_max=1900&chunk_languages=ces&view=visualizations')
    expect(counts.documents).toBe(1) // the view switch did not search again

    // Zooming changes only the chart: no new count, the same URL.
    await page.getByTestId('timeline-zoom-in').click()
    await expect(page.getByTestId('timeline-reset')).toBeEnabled()
    await page.getByTestId('timeline-reset').click()
    expect(counts.distributions).toBe(1)
    expect(hash(page)).toBe('#/search?year_max=1900&chunk_languages=ces&view=visualizations')

    // A draft edit stays pending across view switches and Back/Forward keep the kept answers.
    await input(page).fill('Lhota')
    await expect(page.getByTestId('search-pending')).toBeVisible()
    await page.goBack()
    await expect(documentTitles(page)).toHaveText(['1. Kronika obce Lhota'])
    expect(hash(page)).toBe('#/search?year_max=1900&chunk_languages=ces')
    await page.goForward()
    await expect(page.getByTestId('charts-total')).toHaveText('1')
    expect([counts.documents, counts.distributions, counts.passages]).toEqual([1, 1, 0])

    // Removing a chip applies at once in either view; the charts count the new criteria.
    await input(page).fill('')
    await chip(page, 'Language: Czech').locator('.q-chip__icon--remove').click()
    await expect(page.getByTestId('charts-total')).toHaveText('1')
    expect(counts.distributions).toBe(2)
    expect(hash(page)).toBe('#/search?year_max=1900&view=visualizations')

    // Clear all: every document, still in Visualizations.
    await page.getByTestId('search-clear-all').click()
    await expect(page.getByTestId('charts-total')).toHaveText('3')
    await expect(page.getByTestId('charts-scope')).toContainText('the whole searchable corpus')
    expect(hash(page)).toBe('#/search?view=visualizations')
    await viewTab(page, 'results').click()
    await expect(documentTitles(page)).toHaveCount(3)
    expect(hash(page)).toBe('#/search?mode=documents')

    // Nothing overflows the page horizontally.
    await viewTab(page, 'visualizations').click()
    await expect(page.getByTestId('charts-total')).toHaveText('3')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
  })
}

test('a timeline period applied as a filter changes the criteria of both views', async ({ page }) => {
  const counts = countRequests(page)
  await openSearch(page, '/#/search?view=visualizations')
  await expect(page.getByTestId('charts-total')).toHaveText('3')
  await expect(page.getByTestId('timeline-window')).toHaveText('1850–1909 · single years')
  await page.getByTestId('timeline-apply-period').click()
  await expect(page.getByTestId('charts-total')).toHaveText('2')
  await expect(chip(page, '1850-1909')).toBeVisible()
  expect(hash(page)).toBe('#/search?year_min=1850&year_max=1909&view=visualizations')
  await viewTab(page, 'results').click()
  await expect(documentTitles(page)).toHaveCount(2)
  expect(counts.documents).toBe(1)
})

test('filter-only passages and a failed count are stated, never charted as the corpus', async ({ page }) => {
  const counts = countRequests(page)
  await openSearch(page, '/#/search?chunk_languages=ces&mode=passages&view=visualizations')
  await expect(page.getByTestId('charts-passages')).toBeVisible()
  expect(counts.distributions).toBe(0)
  await page.getByTestId('charts-show-documents').click()
  await expect(page.getByTestId('charts-total')).toHaveText('3')
  expect(hash(page)).toBe('#/search?chunk_languages=ces&view=visualizations')

  let fail = true
  await page.route('**/api/analytics/corpus/distributions', (route) =>
    fail ? route.fulfill({ status: 503, json: { detail: 'Weaviate unavailable' } }) : route.continue())
  await openSearch(page, '/#/search?year_max=1900&view=visualizations')
  await expect(page.getByTestId('charts-error')).toBeVisible()
  await expect(page.getByTestId('corpus-years')).toHaveCount(0)
  fail = false
  await page.getByTestId('charts-retry').click()
  await expect(page.getByTestId('charts-total')).toHaveText('1')
})

test('signing out drops the collection scope and charts the public corpus for the same criteria', async ({ page }) => {
  // Review of #621: the collection state must not stay, nor a spinner without a request.
  await ensureLoggedIn(page, 'owner')
  const counts = countRequests(page)
  await openSearch(page, '/#/search?year_max=1900')
  await expect(documentTitles(page)).toHaveText(['1. Kronika obce Lhota'])
  await page.getByRole('button', { name: 'Search filters' }).click()
  await page.getByLabel('Select a Collection').click()
  await page.getByRole('option', { name: 'Kroniky a dopisy' }).click()
  await page.getByRole('button', { name: 'Search filters' }).click()
  const scoped = page.waitForRequest(isDocumentSearch)
  await input(page).press('Enter')
  expect((await scoped).postDataJSON().user_collection_id).toBeTruthy()
  await expect(chip(page, 'Kroniky a dopisy')).toBeVisible()

  await viewTab(page, 'visualizations').click()
  await expect(page.getByTestId('charts-collection')).toBeVisible()
  expect(counts.distributions).toBe(0)

  const counted = page.waitForRequest(isDistributions)
  await logOut(page)
  expect((await counted).postDataJSON()).toEqual({ filters: { year_min: null, year_max: 1900, title_contains: [], libraries: [], languages: [] } })
  await expect(page.getByTestId('charts-total')).toHaveText('1')
  await expect(page.getByTestId('charts-collection')).toHaveCount(0)
  await expect(chip(page, 'Kroniky a dopisy')).toHaveCount(0)
  expect(hash(page)).toBe('#/search?year_max=1900&view=visualizations')
})

const GAZETTE = 'Pražský věstník'
const RANKED_ROUTE = '**/api/analytics/results/distributions'

for (const viewport of ['wide', 'phone'] as const) {
  test(`a text query's charts count the ranking the Results hold, in each mode's unit (${viewport})`, async ({ page }) => {
    await useViewport(page, viewport)
    const counts = countRequests(page)
    const searched = page.waitForResponse(r => isPassageSearch(r.url(), r.request().method()))
    await openSearch(page, '/#/search?q=Lhota')
    const ranking: string[] = (await (await searched).json()).ranked_ids
    await expect(page.getByTestId('search-coverage')).toContainText('All 7 matching passages.')

    // The same ranked ids, criteria and ranking: counted, not searched again.
    const counted = page.waitForRequest(isRankedCount)
    await viewTab(page, 'visualizations').click()
    expect((await counted).postDataJSON()).toMatchObject({
      mode: 'passages', ids: ranking, criteria: { text_query: 'Lhota' }, ranking: { type: 'hybrid', bounded: false }, members: true
    })
    await expect(page.getByTestId('charts-total')).toHaveText('7')
    await expect(page.getByTestId('charts-scope')).toContainText('passages counted: the ranked passages of this search, not the whole corpus')
    await expect(page.getByTestId('charts-distinct-documents')).toContainText('the 7 passages come from 3 distinct documents')
    await expect(page.getByTestId('charts-ranking')).toContainText('Every matching passage was retrieved')
    await expect(page.getByTestId('charts-unit')).toHaveText('Charts of the ranked passages of this search.')
    await expect(page.getByTestId('results-years')).toContainText('5 of 7 passages (71.4 %) have a publication year')
    await expect(page.getByTestId('results-libraries')).toContainText('0 of 7 passages')
    expect(hash(page)).toBe('#/search?q=Lhota&view=visualizations')
    expect([counts.passages, counts.ranked, counts.distributions]).toEqual([1, 1, 0])

    // A pending edit changes neither the charts nor their labels.
    await input(page).fill('Brno')
    await expect(page.getByTestId('search-pending')).toBeVisible()
    await expect(page.getByTestId('charts-total')).toHaveText('7')
    await input(page).fill('Lhota')

    // Documents: its own ranking, counted as distinct documents.
    await page.getByTestId('results-mode-documents').click()
    await expect(page.getByTestId('charts-scope')).toContainText('documents counted: the ranked documents of this search')
    await expect(page.getByTestId('charts-total')).toHaveText('3')
    await expect(page.getByTestId('charts-distinct-documents')).toHaveCount(0)
    expect(hash(page)).toBe('#/search?q=Lhota&mode=documents&view=visualizations')
    expect([counts.documents, counts.ranked]).toEqual([1, 2])

    // Inspecting the undated documents lists the gazette, numbered by its rank, of the same ranking.
    await page.getByTestId('timeline-inspect-unknown').click()
    await expect(page.getByTestId('inspection-label')).toHaveText('Inspecting the documents without a valid publication year')
    await expect(page.getByTestId('inspection-count')).toContainText('1 of the 3 counted documents of this search')
    await expect(documentTitles(page)).toHaveText([new RegExp(`^[123]\\. ${GAZETTE}$`)])
    expect(hash(page)).toBe('#/search?q=Lhota&mode=documents&inspect=year:~unknown')
    expect([counts.documents, counts.ranked, counts.reads]).toEqual([1, 2, 1])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)

    // Back to the charts, Forward to the inspection: the kept answers.
    await page.goBack()
    await expect(page.getByTestId('charts-total')).toHaveText('3')
    await page.goForward()
    await expect(page.getByTestId('inspection-label')).toBeVisible()

    // The reader and its way back keep the inspection and the ranking.
    await documentTitles(page).click()
    await expect(page).toHaveURL(new RegExp(`#/documents/${fixture.document('gazette').id}\\?.*from=search`))
    await page.getByRole('link', { name: 'Back to search results' }).click()
    await expect(documentTitles(page)).toHaveText([new RegExp(`${GAZETTE}$`)])
    expect(hash(page)).toBe('#/search?q=Lhota&mode=documents&inspect=year:~unknown')
    await page.getByTestId('inspection-clear').click()
    await expect(documentTitles(page)).toHaveCount(3)
    expect(hash(page)).toBe('#/search?q=Lhota&mode=documents')
    expect([counts.documents, counts.passages, counts.ranked]).toEqual([1, 1, 2])
  })
}

test('an inspected period lists its passages of the ranking; applying it as a filter is a new search', async ({ page }) => {
  const counts = countRequests(page)
  await openSearch(page, '/#/search?q=Lhota&view=visualizations')
  await expect(page.getByTestId('charts-total')).toHaveText('7')
  const read = page.waitForRequest(isRead)
  await page.getByTestId('timeline-inspect-bin-1851').click()
  // The chronicle's passages (1851), read by id.
  const chronicle = fixture.document('chronicle').chunks.map((c: { id: string }) => c.id)
  expect([...(await read).postDataJSON().ids].sort()).toEqual([...chronicle].sort())
  await expect(page.getByTestId('inspection-count')).toContainText('3 of the 7 counted passages')
  await expect(page.locator('[data-testid="inspection"] .search-result__title')).toHaveCount(3)
  await expect(page.locator('[data-testid="inspection"] [role="checkbox"]')).toHaveCount(0)
  expect(hash(page)).toBe('#/search?q=Lhota&inspect=year:1851')
  expect([counts.passages, counts.ranked]).toEqual([1, 1])

  // Back to the charts, then a period as a filter: new criteria, a new search and count.
  await page.getByTestId('inspection-charts').click()
  await expect(page.getByTestId('charts-total')).toHaveText('7')
  await page.getByTestId('timeline-apply-period').click()
  await expect(chip(page, '1850-1909')).toBeVisible()
  await expect(page.getByTestId('charts-total')).toHaveText('5')
  expect([counts.passages, counts.ranked]).toEqual([2, 2])
})

test('a bounded ranking is labelled bounded, and a failed count can be retried without searching again', async ({ page }) => {
  // The search's retrieval limit cuts the ranking to three passages.
  await page.route('**/api/search/passages', async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    await route.fulfill({ response, json: { ...body, ranked_ids: body.ranked_ids.slice(0, 3), bounded: true, total_count: null } })
  })
  let fail = true
  await page.route(RANKED_ROUTE, (route) => (fail ? route.fulfill({ status: 503, json: { detail: 'Weaviate unavailable' } }) : route.continue()))
  const counts = countRequests(page)
  await openSearch(page, '/#/search?q=Lhota&view=visualizations')
  await expect(page.getByTestId('charts-error')).toContainText('Weaviate unavailable')
  await expect(page.getByTestId('results-years')).toHaveCount(0)
  fail = false
  const counted = page.waitForRequest(isRankedCount)
  await page.getByTestId('charts-retry').click()
  const request = (await counted).postDataJSON()
  expect([request.ids.length, request.ranking.bounded]).toEqual([3, true])
  await expect(page.getByTestId('charts-total')).toHaveText('3')
  await expect(page.getByTestId('charts-ranking')).toContainText('Bounded: only the best 3 by relevance were retrieved')
  expect([counts.passages, counts.ranked]).toEqual([1, 2])
})

test('inspected results deleted since the ranking are stated, not shown as an empty list', async ({ page }) => {
  await page.route('**/api/search/passages/read', (route) => route.fulfill({ json: { items: [], time_spent: 0 } }))
  await openSearch(page, '/#/search?q=Lhota&inspect=language:ces')
  await expect(page.getByTestId('inspection-count')).toContainText('7 of the 7 counted passages')
  await expect(page.getByTestId('inspection-gone')).toContainText('These results no longer exist')
})
