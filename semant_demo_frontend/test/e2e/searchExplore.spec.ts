import { expect, test, type Page, type Request } from '@playwright/test'

import { closePhoneNavigation, fixture, isPassageSearch, useViewport } from './support'

// The Search page evolving into Explore Results (#605): draft and applied criteria, the
// applied search in the URL (reload, Back/Forward, shared links), Passages loaded page by
// page with their coverage, late answers dropped, and the reader's way back to the search.

const input = (page: Page) => page.getByRole('combobox', { name: 'Search query' })
const chip = (page: Page, text: string) => page.locator('.active-filter-chip', { hasText: text })
const nextSearch = (page: Page): Promise<Request> => page.waitForRequest((r) => isPassageSearch(r.url(), r.method()))
const hash = (page: Page) => decodeURIComponent(new URL(page.url()).hash).replace(/\+/g, ' ')

async function openSearch (page: Page, path = '/#/search') {
  await page.goto(path)
  await closePhoneNavigation(page)
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
  await openSearch(page, '/#/search?q=Lhota&year_min=soon&chunk_classifications=complexity:trivial&mode=documents')
  const criteria = (await sent).postDataJSON().criteria
  expect(criteria).toMatchObject({ text_query: 'Lhota', document_filters: { year_min: null }, chunk_filters: { classifications: {} } })
  await expect(page.getByText('Left out of the search because they are not valid: Publication year from: soon')).toBeVisible()
  await expect(page.getByText(/Left out of the search because they are not available: Complexity: trivial, Documents results/)).toBeVisible()
  await expect(page.locator('#result-1')).toBeVisible()
  await expect.poll(() => hash(page)).toBe('#/search?q=Lhota')
})

test('Load more continues the ranking up to its end and says what the results cover', async ({ page }) => {
  // Pages of three: the server pages the real results, so Load more reaches the next ones.
  const offsets: number[] = []
  await page.route('**/api/search/passages', async (route) => {
    const body = route.request().postDataJSON()
    offsets.push(body.offset)
    await route.continue({ postData: JSON.stringify({ ...body, limit: 3 }) })
  })
  await openSearch(page)
  await searchFor(page, 'Lhota')
  const coverage = page.getByTestId('search-coverage')
  await expect(page.locator('.search-result')).toHaveCount(3)
  await expect(coverage).toContainText('7 matching passages (3 shown).') // the whole ranking is known at once

  const more = page.getByTestId('search-load-more')
  await more.click()
  await expect(page.locator('.search-result')).toHaveCount(6)
  await more.click()
  await expect(page.locator('.search-result')).toHaveCount(7) // every fixture chunk, once
  await expect(more).toHaveCount(0)
  await expect(coverage).toContainText('All 7 matching passages.')
  expect(offsets).toEqual([0, 3, 6])
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
