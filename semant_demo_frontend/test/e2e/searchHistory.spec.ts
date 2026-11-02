import { expect, test, type Page, type Request } from '@playwright/test'

import { closePhoneNavigation, ensureLoggedIn, logOut, search, useViewport } from './support'

// Recent searches under the Search page's query field (#558): kept in this browser, one
// history per signed-in user and one for signed-out use, run again with their criteria.

const input = (page: Page) => page.getByRole('combobox', { name: 'Search query' })
const dropdown = (page: Page) => page.getByTestId('search-history')
const entries = (page: Page) => page.getByTestId('search-history-entry')

/** Resolves to the next search request the page sends. */
function nextSearch (page: Page): Promise<Request> {
  return page.waitForRequest((r) => r.url().endsWith('/api/search') && r.method() === 'POST')
}

/** A fresh load of the Search page (an empty query field), keeping the session. */
async function openSearchPage (page: Page) {
  await page.goto('/#/search')
  await page.reload()
  await closePhoneNavigation(page)
}

test('recent searches open on click, narrow while typing and run again', async ({ page }) => {
  await search(page, 'Lhota')
  await search(page, 'Brno')

  // The page's own autofocus does not open the list; a click does.
  await openSearchPage(page)
  await expect(input(page)).toBeFocused()
  await expect(dropdown(page)).toHaveCount(0)
  await input(page).click()
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
  expect((await rerun).postDataJSON().query).toBe('Lhota')
  await expect(dropdown(page)).toHaveCount(0)
  await expect(page.locator('#result-1')).toBeVisible()

  // The field holds the query that ran, which narrows the list to it; emptied, the list
  // shows the search that ran again at the top. Escape closes it.
  await input(page).click()
  await expect(entries(page)).toHaveText([/Lhota/])
  await input(page).fill('')
  await expect(entries(page)).toHaveText([/Lhota/, /Brno/])
  await input(page).press('Escape')
  await expect(dropdown(page)).toHaveCount(0)

  // A click on an entry runs it.
  await input(page).click()
  await expect(entries(page)).toHaveText([/Lhota/, /Brno/])
  const clicked = nextSearch(page)
  await entries(page).filter({ hasText: 'Brno' }).click()
  expect((await clicked).postDataJSON().query).toBe('Brno')

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
  await input(page).click()
  await expect(entries(page).first()).toContainText('Lhota')
  await expect(entries(page).first()).toContainText('Embedding: Fake small')
  const rerun = nextSearch(page)
  await entries(page).first().click()
  const body = (await rerun).postDataJSON()
  expect([body.query, body.vector, body.searchTitleGenerate ?? body.search_title_generate]).toEqual(['Lhota', 'fake-small', false])
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
  await input(page).click()
  await expect(entries(page).first()).toBeInViewport({ ratio: 1 })
  const box = await dropdown(page).boundingBox()
  expect(box && box.x >= 0 && box.x + box.width <= (page.viewportSize()?.width ?? 0)).toBe(true)
  const rerun = nextSearch(page)
  await entries(page).first().click()
  expect((await rerun).postDataJSON().query).toBe('Lhota')
})
