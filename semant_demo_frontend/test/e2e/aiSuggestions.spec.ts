import { expect, test, type Page } from '@playwright/test'
import { chunkText, deleteSuggestions, fixture, logIn, openDocument } from './support'

// Request-scoped AI suggestions in the document view (ADR 0003/0007). The fake Topicer
// streams one chunk event, then waits FAKE_TOPICER_STREAM_DELAY (3 s) before the next, so
// the run is still under way when the test acts. Runs save suggestions: each test deletes
// the unresolved "person" suggestions it created (fixture spans have other tags or types).

async function startPersonRun (page: Page) {
  await page.getByRole('tab', { name: 'AI assist' }).click()
  await page.locator('.ai-tag-list').getByText(fixture.tag('person').name, { exact: true }).click()
  await page.getByRole('button', { name: 'Run AI' }).click()
}

// Suggestion cards of this run's tag (the fixture has an unresolved "place" suggestion too).
const suggestionCards = (page: Page) =>
  page.locator('.auto-span-card').filter({ hasText: fixture.tag('person').name })

test.afterEach(async ({ request }) => {
  await deleteSuggestions(request, 'owner', 'chronicles', 'chronicle', 'person')
})

test('suggestions appear while the run is under way and cancelling keeps them', async ({ page }) => {
  await logIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await startPersonRun(page)

  // The first chunk's suggestion is shown before the run ends.
  await expect(page.getByText('Processed 1 chunks', { exact: false })).toBeVisible()
  await expect(suggestionCards(page)).toHaveCount(1)
  await expect(page.getByRole('button', { name: 'Cancel' })).toBeVisible()

  await page.getByRole('button', { name: 'Cancel' }).click()
  await expect(page.getByText('Cancelled; saved suggestions are kept.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Run AI' })).toBeVisible()

  // Saved suggestions survive a reload; the cancelled rest of the run was never saved.
  await page.reload()
  await page.getByRole('tab', { name: 'AI assist' }).click()
  await expect(chunkText(page, 'chronicle_1')).toBeVisible()
  await expect(suggestionCards(page)).toHaveCount(1)
})

test('leaving the document during a run shows nothing of it in the next view', async ({ page }) => {
  await logIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await startPersonRun(page)
  await expect(suggestionCards(page)).toHaveCount(1)

  // Same document in another collection, while the run still waits for its second chunk.
  await openDocument(page, 'newspapers', 'chronicle')
  await page.getByRole('tab', { name: 'AI assist' }).click()

  await expect(page.getByRole('button', { name: 'Run AI' })).toBeVisible()
  await expect(page.getByText('Processed', { exact: false })).toHaveCount(0)
  await expect(suggestionCards(page)).toHaveCount(0)
  await expect(chunkText(page, 'chronicle_3')).toBeVisible()

  // Back in the original collection: the suggestion saved before leaving is there; the
  // run ended with the request, so the second chunk got none.
  await openDocument(page, 'chronicles', 'chronicle')
  await page.getByRole('tab', { name: 'AI assist' }).click()
  await expect(suggestionCards(page)).toHaveCount(1)
})
