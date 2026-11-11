import { expect, test, type Page, type Request } from '@playwright/test'

import { ensureLoggedIn, isPassageSearch, logOut, search, useViewport } from './support'

// Recent searches under the Search page's query field (#558): kept in this browser, one
// history per signed-in user and one for signed-out use, run again with their criteria.

const input = (page: Page) => page.getByRole('combobox', { name: 'Search query' })
const dropdown = (page: Page) => page.getByTestId('search-history')
const entries = (page: Page) => page.getByTestId('search-history-entry')

/** Resolves to the next search request the page sends. */
function nextSearch (page: Page): Promise<Request> {
  return page.waitForRequest((r) => isPassageSearch(r.url(), r.method()))
}

/** A fresh load of the Search page (an empty query field), keeping the session. */
async function openSearchPage (page: Page) {
  await page.goto('/#/search')
  await page.reload()
}

/**
 * Opens the list once the search options are loaded (an entry picked before then is not
 * run; a test of that holds the options itself).
 */
async function openHistory (page: Page) {
  await input(page).click()
  await expect(dropdown(page)).toBeVisible()
  await expect(page.getByTestId('search-history-note')).toHaveCount(0)
}

test('recent searches open on click, narrow while typing and run again', async ({ page }) => {
  await search(page, 'Lhota')
  await search(page, 'Brno')

  // The page's own autofocus does not open the list; a click does.
  await openSearchPage(page)
  await expect(input(page)).toBeFocused()
  await expect(dropdown(page)).toHaveCount(0)
  await openHistory(page)
  await expect(entries(page)).toHaveText([/Brno/, /Lhota/])
  await expect(input(page)).toHaveAttribute('aria-expanded', 'true')

  await input(page).fill('lho')
  await expect(entries(page)).toHaveText([/Lhota/])
  await input(page).fill('')

  // Keyboard: the second entry, Enter runs it.
  await input(page).press('ArrowDown')
  await input(page).press('ArrowDown')
  await expect(entries(page).nth(1)).toHaveAttribute('aria-selected', 'true')
  const rerun = nextSearch(page)
  await input(page).press('Enter')
  expect((await rerun).postDataJSON().criteria.text_query).toBe('Lhota')
  await expect(dropdown(page)).toHaveCount(0)
  await expect(page.locator('#result-1')).toBeVisible()

  // The field still holds the query that ran; opened, the list shows the whole history,
  // the search that ran again at the top. Escape closes it.
  await input(page).click()
  await expect(entries(page)).toHaveText([/Lhota/, /Brno/])
  await input(page).press('Escape')
  await expect(dropdown(page)).toHaveCount(0)

  // A click on an entry runs it.
  await input(page).click()
  await expect(entries(page)).toHaveText([/Lhota/, /Brno/])
  const clicked = page.waitForResponse((r) => isPassageSearch(r.url(), r.request().method()))
  await entries(page).filter({ hasText: 'Brno' }).click()
  expect((await clicked).request().postDataJSON().criteria.text_query).toBe('Brno')
  await expect(page.locator('#result-1')).toBeVisible() // saved once its results arrived

  // Remove one entry, then clear the history.
  await input(page).fill('')
  await entries(page).filter({ hasText: 'Lhota' }).getByRole('button', { name: 'Remove from history: Lhota' }).click()
  await expect(entries(page)).toHaveText([/Brno/])
  await page.getByTestId('search-history-clear').click()
  await expect(dropdown(page)).toHaveCount(0)
  await openSearchPage(page)
  await input(page).click()
  await expect(dropdown(page)).toHaveCount(0)
})

test('reopened after several searches, the list shows every one of them, unchanged (#608 review)', async ({ page }) => {
  const queries = ['Lhota', 'Brno', 'Praha', 'mlýn']
  await openSearchPage(page)
  for (const query of queries) {
    await input(page).fill(query)
    const ran = page.waitForResponse((r) => isPassageSearch(r.url(), r.request().method()))
    await input(page).press('Enter')
    await ran
    await expect(page.locator('#result-1')).toBeVisible()
  }
  await expect(input(page)).toHaveValue('mlýn')

  // The field holds the last query; a click lists the whole history, newest first.
  const newestFirst = [...queries].reverse()
  await page.keyboard.press('Escape')
  await openHistory(page)
  await expect(page.getByTestId('search-history-entry').locator('.search-history__query')).toHaveText(newestFirst)

  // Typing narrows it; closed and opened again, everything is back, with its own query.
  await input(page).fill('Br')
  await expect(entries(page)).toHaveText([/Brno/])
  await input(page).press('Escape')
  await input(page).fill('mlýn')
  await input(page).press('Escape')
  await page.locator('body').click({ position: { x: 5, y: 5 } })
  await openHistory(page)
  await expect(page.getByTestId('search-history-entry').locator('.search-history__query')).toHaveText(newestFirst)

  // An older entry runs its own query, not the one in the field.
  const rerun = nextSearch(page)
  await entries(page).filter({ hasText: 'Brno' }).click()
  expect((await rerun).postDataJSON().criteria.text_query).toBe('Brno')
  await expect(input(page)).toHaveValue('Brno')
  await expect(page.locator('#result-1')).toBeVisible()
  await openHistory(page)
  await expect(page.getByTestId('search-history-entry').locator('.search-history__query')).toHaveText(['Brno', 'mlýn', 'Praha', 'Lhota'])
})

test('a search from the history runs with its criteria', async ({ page }) => {
  await openSearchPage(page)
  await input(page).fill('Lhota')
  await page.getByRole('button', { name: 'Search filters' }).click()
  await page.getByTestId('search-vector-select').click()
  await page.getByRole('option', { name: /Fake small/ }).click()
  const first = nextSearch(page)
  await input(page).press('Enter')
  expect((await first).postDataJSON().vector).toBe('fake-small')
  await expect(page.locator('#result-1')).toBeVisible()

  // A fresh page uses the default vector; the history entry restores the chosen one.
  await openSearchPage(page)
  await openHistory(page)
  await expect(entries(page).first()).toContainText('Lhota')
  await expect(entries(page).first()).toContainText('Embedding: Fake small')
  const rerun = nextSearch(page)
  await entries(page).first().click()
  const body = (await rerun).postDataJSON()
  // No generated titles or summaries: a passage search asks for none.
  expect([body.criteria.text_query, body.vector, 'search_title_generate' in body]).toEqual(['Lhota', 'fake-small', false])
  await expect(page.locator('.active-filter-chip', { hasText: 'Embedding: Fake small' })).toBeVisible()
})

test('each user and signed-out use have their own history, kept after signing out', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await search(page, 'Lhota')

  await logOut(page)
  await openSearchPage(page)
  await input(page).click()
  await expect(dropdown(page)).toHaveCount(0)
  await search(page, 'Brno')

  await ensureLoggedIn(page, 'annotator')
  await openSearchPage(page)
  await input(page).click()
  await expect(dropdown(page)).toHaveCount(0)

  await ensureLoggedIn(page, 'owner')
  await openSearchPage(page)
  await input(page).click()
  await expect(entries(page)).toHaveText([/Lhota/])

  await logOut(page)
  await openSearchPage(page)
  await input(page).click()
  await expect(entries(page)).toHaveText([/Brno/])
})

test('recent searches are usable at phone width', async ({ page }) => {
  await useViewport(page, 'phone')
  await search(page, 'Lhota')
  await openSearchPage(page)
  await openHistory(page)
  await expect(entries(page).first()).toBeInViewport({ ratio: 1 })
  const box = await dropdown(page).boundingBox()
  expect(box && box.x >= 0 && box.x + box.width <= (page.viewportSize()?.width ?? 0)).toBe(true)
  const rerun = nextSearch(page)
  await entries(page).first().click()
  expect((await rerun).postDataJSON().criteria.text_query).toBe('Lhota')
})

/** Counts the search requests the page sends from now on. */
function countSearches (page: Page): () => number {
  let count = 0
  page.on('request', (r) => { if (isPassageSearch(r.url(), r.method())) count++ })
  return () => count
}

test('only searches that ran are saved; a too long query is refused, not sent', async ({ page }) => {
  await search(page, 'Lhota')

  // A failed search is not remembered.
  await page.route('**/api/search/passages', (route) => route.fulfill({ status: 500, body: 'failure' }))
  await input(page).fill('Brno')
  await input(page).press('Enter')
  await expect(page.getByText('Search failed')).toBeVisible()
  await page.unroute('**/api/search/passages')

  // Longer than the search criteria allow (1000 characters, #526): refused before searching.
  const searches = countSearches(page)
  await input(page).fill('Lhota '.repeat(200).trim())
  await input(page).press('Enter')
  await expect(page.getByText('The text query can be at most 1,000 characters long.')).toBeVisible()
  expect(searches()).toBe(0)

  await openSearchPage(page)
  await input(page).click()
  await expect(entries(page)).toHaveText([/Lhota/])
})

test('an entry runs only once the search options are loaded', async ({ page }) => {
  await search(page, 'Lhota')

  // Hold the filters answer: the list says why picking an entry does not run it yet.
  let release: () => void = () => undefined
  const held = new Promise<void>((resolve) => { release = resolve })
  await page.route('**/api/search/filters', async (route) => { await held; await route.continue() })
  await openSearchPage(page)
  const searches = countSearches(page)
  await input(page).click()
  await expect(page.getByTestId('search-history-note')).toContainText('Loading search options')
  await entries(page).first().click()
  await expect(page.getByText('Search options are still loading. Try again in a moment.')).toBeVisible()
  expect(searches()).toBe(0)

  release()
  await input(page).click()
  await expect(page.getByTestId('search-history-note')).toHaveCount(0)
  const rerun = nextSearch(page)
  await entries(page).first().click()
  expect((await rerun).postDataJSON().criteria.text_query).toBe('Lhota')
})

test('an entry is not run when the search options could not be loaded', async ({ page }) => {
  await search(page, 'Lhota')
  await page.route('**/api/search/filters', (route) => route.fulfill({ status: 500, body: 'failure' }))
  await openSearchPage(page)
  const searches = countSearches(page)
  await input(page).click()
  await entries(page).first().click()
  await expect(page.getByText('This search cannot be restored because the search options could not be loaded.')).toBeVisible()
  expect(searches()).toBe(0)
})

test('the history cannot be cleared while a search is running', async ({ page }) => {
  await search(page, 'Lhota')

  // Hold the next search's answer.
  let release: () => void = () => undefined
  const held = new Promise<void>((resolve) => { release = resolve })
  await page.route('**/api/search/passages', async (route) => { await held; await route.continue() })
  await input(page).fill('Brno')
  await input(page).press('Enter')
  await input(page).fill('')
  await expect(entries(page)).toHaveText([/Lhota/])
  await page.getByTestId('search-history-clear').click()
  await expect(page.getByText('A search is running. The history cannot be cleared until it finishes.')).toBeVisible()
  await expect(entries(page)).toHaveText([/Lhota/])

  // Once it finished, it is saved and the history can be cleared.
  release()
  await expect(page.locator('#result-1')).toBeVisible()
  await page.unroute('**/api/search/passages')
  await input(page).click()
  await expect(entries(page)).toHaveText([/Brno/, /Lhota/])
  await page.getByTestId('search-history-clear').click()
  await expect(dropdown(page)).toHaveCount(0)
  await openSearchPage(page)
  await input(page).click()
  await expect(dropdown(page)).toHaveCount(0)
})

test('a history saved by a newer version asks for a reload, is not written over and can be cleared', async ({ page }) => {
  await search(page, 'Lhota')
  // Pretend a newer version of the application wrote this browser's history meanwhile.
  const newer = await page.evaluate(() => {
    const key = Object.keys(localStorage).find(k => k.startsWith('semant.searchHistory.search.')) as string
    const value = JSON.stringify({ ...JSON.parse(localStorage.getItem(key) ?? '{}'), criteriaVersion: 99 })
    localStorage.setItem(key, value)
    return { key, value }
  })

  await input(page).fill('')
  await expect(page.getByTestId('search-history-reload')).toContainText('Reload the page to see them.')
  await expect(entries(page)).toHaveCount(0)
  await input(page).fill('Brno')
  const answer = page.waitForResponse((r) => isPassageSearch(r.url(), r.request().method()))
  await input(page).press('Enter')
  expect((await answer).status()).toBe(200)
  await expect(page.locator('#result-1')).toBeVisible()
  expect(await page.evaluate((key) => localStorage.getItem(key), newer.key)).toBe(newer.value)

  // Reloading does not help here (no newer version runs); the history can be cleared instead.
  await openSearchPage(page)
  await input(page).click()
  await expect(page.getByTestId('search-history-reload')).toBeVisible()
  await page.getByTestId('search-history-clear').click()
  await expect(dropdown(page)).toHaveCount(0)
  expect(await page.evaluate((key) => localStorage.getItem(key), newer.key)).toBeNull()
  await search(page, 'Lhota')
  await openSearchPage(page)
  await input(page).click()
  await expect(entries(page)).toHaveText([/Lhota/])
})
