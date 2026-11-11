import { expect, test, type Page, type Request } from '@playwright/test'

import { fixture, isPassageSearch } from './support'

// Search vectors (#217): the browser-test profile configures the test store's two named
// chunk vectors, `fake-default` (the default) and `fake-small`, both embedded by the fake
// providers. The Search page offers them and sends no selection for the default.

const QUERY = fixture.chunk('gazette_1').text

async function openFilters (page: Page) {
  await page.goto('/#/search')
  await page.getByRole('combobox', { name: 'Search query' }).fill(QUERY)
  await page.getByRole('button', { name: 'Search filters' }).click()
}

async function runSearch (page: Page): Promise<{ request: Request, body: { vector: string | null, items: { id: string }[] } }> {
  const answer = page.waitForResponse((r) => isPassageSearch(r.url(), r.request().method()))
  await page.getByRole('combobox', { name: 'Search query' }).press('Enter')
  const response = await answer
  expect(response.status()).toBe(200)
  await expect(page.locator('#result-1')).toBeVisible()
  return { request: response.request(), body: await response.json() }
}

test('search uses the default vector unless another is chosen', async ({ page }) => {
  await openFilters(page)
  const select = page.getByTestId('search-vector-select')
  await expect(select).toContainText('Fake default (default)')

  const byDefault = await runSearch(page)
  expect(byDefault.request.postDataJSON().vector).toBeNull()
  expect(byDefault.body.vector).toBe('fake-default')
  expect(byDefault.body.items[0].id).toBe(fixture.chunk('gazette_1').id)

  await select.click()
  await page.getByRole('option', { name: /Fake small/ }).click()
  // A draft until applied: the chips show the applied search.
  await expect(page.locator('.active-filter-chip', { hasText: 'Embedding: Fake small' })).toHaveCount(0)

  const chosen = await runSearch(page)
  expect(chosen.request.postDataJSON().vector).toBe('fake-small')
  expect(chosen.body.vector).toBe('fake-small')
  expect(chosen.body.items[0].id).toBe(fixture.chunk('gazette_1').id)
  await expect(page.locator('.active-filter-chip', { hasText: 'Embedding: Fake small' })).toBeVisible()
  expect(new URL(page.url()).hash).toContain('vector=fake-small')

  // Removing the chip searches again with the default, sent as no selection.
  const again = page.waitForRequest((r) => isPassageSearch(r.url(), r.method()))
  await page.locator('.active-filter-chip', { hasText: 'Embedding: Fake small' }).locator('.q-chip__icon--remove').click()
  expect((await again).postDataJSON().vector).toBeNull()
  await expect(select).toContainText('Fake default (default)')
  expect(new URL(page.url()).hash).not.toContain('vector=')
})
