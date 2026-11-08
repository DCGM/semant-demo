import { expect, test, type Page, type Request } from '@playwright/test'

import { closePhoneNavigation, ensureLoggedIn, isPassageSearch, logOut, useViewport } from './support'

// Explore Visualizations, first slice (#618): a Results | Visualizations switch on the Search page
// over the same applied criteria and results mode, in the URL and history. Without a text query
// the charts count every document the filters match (the Analytics distributions, with the same
// document and per-dimension chunk filters as Documents); other criteria say why they are not
// charted. The fixture corpus has three documents, all `ces`: chronicle 1851, letters 1902 and
// gazette without a year.

const input = (page: Page) => page.getByRole('combobox', { name: 'Search query' })
const chip = (page: Page, text: string) => page.locator('.active-filter-chip', { hasText: text })
const hash = (page: Page) => decodeURIComponent(new URL(page.url()).hash).replace(/\+/g, ' ')
const isDocumentSearch = (r: Request) => new URL(r.url()).pathname.endsWith('/api/search/documents') && r.method() === 'POST'
const isDistributions = (r: Request) => new URL(r.url()).pathname.endsWith('/api/analytics/corpus/distributions') && r.method() === 'POST'
const documentTitles = (page: Page) => page.getByTestId('document-result-open')
const viewTab = (page: Page, view: 'results' | 'visualizations') => page.getByTestId(`view-${view}`)

/** Counts the requests of each kind from now on. */
function countRequests (page: Page) {
  const counts = { documents: 0, passages: 0, distributions: 0 }
  page.on('request', (r) => {
    if (isDocumentSearch(r)) counts.documents++
    else if (isPassageSearch(r.url(), r.method())) counts.passages++
    else if (isDistributions(r)) counts.distributions++
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

test('a text query, filter-only passages and a failed count are stated, never charted as the corpus', async ({ page }) => {
  const counts = countRequests(page)
  await openSearch(page, '/#/search?q=Lhota&view=visualizations')
  await expect(page.getByTestId('charts-text-query')).toContainText('Charts of search results are not available yet.')
  await expect(page.getByTestId('corpus-years')).toHaveCount(0)
  expect([counts.distributions, counts.passages]).toEqual([0, 0]) // nothing searched or counted for a hidden view

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
