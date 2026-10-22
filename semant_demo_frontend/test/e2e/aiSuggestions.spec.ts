import { expect, test, type Page } from '@playwright/test'
import { chunkText, deleteSuggestions, ensureLoggedIn, fixture, openDocument, sidebarPanelButton } from './support'

// Request-scoped AI suggestions in the document view (ADR 0003/0007). The fake Topicer
// streams one chunk event, then waits FAKE_TOPICER_STREAM_DELAY (3 s) before the next, so
// the run is still under way when the test acts. Runs save suggestions: each test deletes
// the unresolved "person" suggestions it created (fixture spans have other tags or types).

async function startPersonRun (page: Page) {
  await sidebarPanelButton(page, 'AI assist').click()
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
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await startPersonRun(page)

  // The first chunk's suggestion is shown before the run ends.
  await expect(page.getByText('Processed 1 chunks', { exact: false })).toBeVisible()
  await expect(suggestionCards(page)).toHaveCount(1)
  await expect(page.getByRole('button', { name: 'Cancel' })).toBeVisible()
  await expect(sidebarPanelButton(page, 'AI assist')).toHaveAttribute('aria-busy', 'true') // the rail shows the run

  await page.getByRole('button', { name: 'Cancel' }).click()
  await expect(page.getByText('Cancelled; saved suggestions are kept.')).toBeVisible()
  await expect(sidebarPanelButton(page, 'AI assist')).not.toHaveAttribute('aria-busy', 'true')
  await expect(page.getByRole('button', { name: 'Run AI' })).toBeVisible()

  // Saved suggestions survive a reload; the cancelled rest of the run was never saved.
  await page.reload()
  await sidebarPanelButton(page, 'AI assist').click()
  await expect(chunkText(page, 'chronicle_1')).toBeVisible()
  await expect(suggestionCards(page)).toHaveCount(1)
})

test('leaving the document during a run shows nothing of it in the next view', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await startPersonRun(page)
  await expect(suggestionCards(page)).toHaveCount(1)

  // Same document in another collection, while the run still waits for its second chunk.
  await openDocument(page, 'newspapers', 'chronicle')
  await sidebarPanelButton(page, 'AI assist').click()

  await expect(page.getByRole('button', { name: 'Run AI' })).toBeVisible()
  await expect(page.getByText('Processed', { exact: false })).toHaveCount(0)
  await expect(suggestionCards(page)).toHaveCount(0)
  await expect(chunkText(page, 'chronicle_3')).toBeVisible()

  // Back in the original collection: the suggestion saved before leaving is there; the
  // run ended with the request, so the second chunk got none.
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI assist').click()
  await expect(suggestionCards(page)).toHaveCount(1)
})

test('a run that may evaluate more than 50 chunks asks first, and Cancel starts nothing', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI assist').click()
  await page.locator('.ai-assist-panel').getByRole('button', { name: 'All' }).click()

  // Optimized: 2 tags × the backend's default limit of 40 chunks per tag.
  await page.getByRole('button', { name: 'Run AI' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('Large AI run')).toBeVisible()
  await expect(dialog.getByText('up to 80 chunks (2 tag(s) × at most 40 chunks per tag)', { exact: false })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Start tagging' })).toBeVisible()

  await dialog.getByRole('button', { name: 'Cancel' }).click()
  await expect(dialog).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Run AI' })).toBeVisible()
  await expect(page.getByText('Processed', { exact: false })).toHaveCount(0)
})

test('the model picked in the panel is used and remembered (#189)', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI assist').click()

  // The fake Topicer lists llm-openrouter (the backend default) and fake-local.
  const picker = page.getByTestId('ai-model-select')
  await expect(picker).toContainText('llm-openrouter (default)')
  await picker.click()
  await page.getByRole('option', { name: 'fake-local' }).click()
  await expect(picker).toContainText('fake-local')

  const sent = page.waitForRequest('**/api/ai/suggest_spans/optimized')
  await page.locator('.ai-tag-list').getByText(fixture.tag('person').name, { exact: true }).click()
  await page.getByRole('button', { name: 'Run AI' }).click()
  expect((await sent).postDataJSON().config_name).toBe('fake-local')
  await expect(suggestionCards(page)).toHaveCount(1)
  await page.getByRole('button', { name: 'Cancel' }).click()

  await page.reload()
  await sidebarPanelButton(page, 'AI assist').click()
  await expect(page.getByTestId('ai-model-select')).toContainText('fake-local')
})
