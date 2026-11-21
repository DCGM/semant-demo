import { expect, test, type Page } from '@playwright/test'
import { chunkText, deleteSuggestions, ensureLoggedIn, fixture, openDocument, sidebarPanelButton } from './support'

// Request-scoped AI suggestions in the document view (ADR 0003/0007). The fake Topicer
// answers the first chunk at once and each further one FAKE_TOPICER_STREAM_DELAY (3 s)
// later, so the run is still under way when the test acts. Runs save suggestions: each test deletes
// the unresolved "person" suggestions it created (fixture spans have other tags or types).

async function openProposalFilters (page: Page) {
  await page.getByTestId('proposal-filters-toggle').click()
  await expect(page.getByTestId('proposal-tag-filter')).toBeVisible()
}

async function startPersonRun (page: Page) {
  await sidebarPanelButton(page, 'AI Tagging').click()
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
  await expect(sidebarPanelButton(page, 'AI Tagging')).toHaveAttribute('aria-busy', 'true') // the rail shows the run

  await page.getByRole('button', { name: 'Cancel' }).click()
  await expect(page.getByText('Cancelled; saved suggestions are kept.')).toBeVisible()
  await expect(sidebarPanelButton(page, 'AI Tagging')).not.toHaveAttribute('aria-busy', 'true')
  await expect(page.getByRole('button', { name: 'Run AI' })).toBeVisible()

  // Saved suggestions survive a reload; the cancelled rest of the run was never saved.
  await page.reload()
  await sidebarPanelButton(page, 'AI Tagging').click()
  await expect(chunkText(page, 'chronicle_1')).toBeVisible()
  await expect(suggestionCards(page)).toHaveCount(1)
})

test('suggestions label their explanation, show creation time, and distinguish Reject from Delete', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await startPersonRun(page)
  const panel = page.locator('.ai-assist-panel')
  const card = suggestionCards(page).first()
  await expect(card).toBeVisible()
  await expect(panel.getByTestId('auto-span-action-note')).toContainText('Reject')
  await expect(panel.getByTestId('auto-span-action-note')).toContainText('Delete')
  await expect(card.getByTestId('ai-suggestion-created')).toContainText('Created:')
  await expect(card.getByTestId('ai-suggestion-explanation-label')).toHaveText('Explanation')
  await page.getByRole('button', { name: 'Cancel' }).click()
})

test('distance sorting keeps AI annotations visible in the reader', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Tagging').click()
  const panel = page.locator('.ai-assist-panel')
  const annotatedText = page.locator('.doc-page .text-segment.is-auto').first()
  await expect(annotatedText).toBeVisible()
  const sort = panel.getByTestId('proposal-sort')
  await sort.click()
  await page.getByRole('option', { name: 'Nearest to current text' }).click()
  await expect(sort).toContainText('Nearest to current text')
  await expect(panel.locator('.auto-span-card')).toHaveCount(1)
  await expect(annotatedText).toBeVisible()
})

test('bulk Delete removes only selected suggestions and leaves other pending suggestions', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await startPersonRun(page)
  await expect(suggestionCards(page)).toHaveCount(1)
  await page.getByRole('button', { name: 'Cancel' }).click()
  await expect(page.getByRole('button', { name: 'Run AI' })).toBeVisible()

  const panel = page.locator('.ai-assist-panel')
  await suggestionCards(page).first().locator('.q-checkbox').click()
  await expect(page.getByTestId('proposal-selection-count')).toHaveText('1 selected')
  await expect(page.getByTestId('proposal-match-count')).toHaveText('2 matches')
  await expect(page.getByTestId('proposal-hidden-count')).toHaveCount(0)
  await panel.getByTestId('bulk-delete-selected').click()
  await expect(suggestionCards(page)).toHaveCount(0)
  await expect(panel.locator('.auto-span-card')).toHaveCount(1)

  await page.reload()
  await sidebarPanelButton(page, 'AI Tagging').click()
  await expect(suggestionCards(page)).toHaveCount(0)
  await expect(panel.locator('.auto-span-card')).toHaveCount(1)
})

test('bulk Delete asks before deleting all pending suggestions', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Tagging').click()
  const panel = page.locator('.ai-assist-panel')
  await panel.locator('.auto-span-bulk-bar .q-checkbox').click()
  await panel.getByTestId('bulk-delete-selected').click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('Delete 1 suggestion?')).toBeVisible()
  await dialog.getByRole('button', { name: 'Cancel' }).click()
  await expect(panel.locator('.auto-span-card')).toHaveCount(1)
})

test('leaving the document during a run shows nothing of it in the next view', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await startPersonRun(page)
  await expect(suggestionCards(page)).toHaveCount(1)

  // Same document in another collection, while the run still waits for its second chunk.
  await openDocument(page, 'newspapers', 'chronicle')
  await sidebarPanelButton(page, 'AI Tagging').click()

  await expect(page.getByRole('button', { name: 'Run AI' })).toBeVisible()
  await expect(page.getByText('Processed', { exact: false })).toHaveCount(0)
  await expect(suggestionCards(page)).toHaveCount(0)
  await expect(chunkText(page, 'chronicle_3')).toBeVisible()

  // Back in the original collection: the suggestion saved before leaving is there; the
  // run ended with the request, so the second chunk got none.
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Tagging').click()
  await expect(suggestionCards(page)).toHaveCount(1)
})

test('a run that may evaluate more than 50 chunks asks first, and Cancel starts nothing', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Tagging').click()
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
  await sidebarPanelButton(page, 'AI Tagging').click()

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
  await sidebarPanelButton(page, 'AI Tagging').click()
  await expect(page.getByTestId('ai-model-select')).toContainText('fake-local')
})

test('proposal filters preserve hidden selection and AI-run tags (#465)', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Tagging').click()
  const panel = page.locator('.ai-assist-panel')
  await openProposalFilters(page)
  const runTagCheckboxes = () => panel.locator('[data-testid="ai-run-options"] .q-checkbox')
    .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('aria-checked')))
  const runTagsBefore = await runTagCheckboxes()
  const tagFilter = page.getByTestId('proposal-tag-filter')
  await expect(panel.locator('.auto-span-card')).toHaveCount(1)
  await panel.locator('.auto-span-bulk-bar .q-checkbox').click()
  await expect(page.getByTestId('proposal-selection-count')).toHaveText('1 selected')
  await expect(page.getByTestId('proposal-hidden-count')).toHaveCount(0)

  await tagFilter.click()
  await page.getByRole('option', { name: fixture.tag('person').name, exact: true }).click()
  await expect(page.getByTestId('no-matching-proposals')).toBeVisible()
  await expect(page.getByTestId('proposal-match-count')).toContainText('0 matches')
  await expect(page.getByTestId('proposal-hidden-count')).toHaveText('(1 hidden)')
  await expect(panel.getByRole('button', { name: 'Confirm' })).toBeEnabled()

  await panel.getByRole('button', { name: 'Reset filters' }).click()
  await expect(panel.locator('.auto-span-card')).toHaveCount(1)
  await expect(page.getByTestId('proposal-selection-count')).toHaveText('1 selected')
  await expect(page.getByTestId('proposal-hidden-count')).toHaveCount(0)
  await panel.getByRole('button', { name: 'Clear selection' }).click()
  await expect(panel.getByRole('button', { name: 'Confirm' })).toBeDisabled()
  expect(await runTagCheckboxes()).toEqual(runTagsBefore)
})

test('keyboard highlight does not approve or select the suggestion (#465)', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Tagging').click()
  const card = page.locator('.auto-span-card').first()
  const highlight = card.getByTestId('proposal-highlight')
  await highlight.focus()
  await highlight.press('Enter')
  await expect(card).toHaveClass(/is-highlighted/)
  await expect(highlight).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('proposal-selection-count')).toContainText('0 selected')
  await expect(page.locator('.auto-span-bulk-bar').getByRole('button', { name: 'Confirm' })).toBeDisabled()
})

test('clicking a gutter annotation reveals a filtered-out proposal and focuses its action (#465)', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Tagging').click()
  await openProposalFilters(page)

  await page.getByTestId('proposal-tag-filter').click()
  await page.getByRole('option', { name: fixture.tag('person').name, exact: true }).click()
  await expect(page.getByTestId('no-matching-proposals')).toBeVisible()

  await page.locator('.gutter-item.is-auto').click()
  await expect(page.getByTestId('proposal-match-count')).toContainText('1 match')
  const card = page.locator('.auto-span-card').first()
  await expect(card).toHaveClass(/is-highlighted/)
  await expect(card.getByTestId('proposal-highlight')).toBeFocused()
  await expect(page.getByTestId('proposal-selection-count')).toContainText('0 selected')
})

test('changing collection/document clears proposal filters and selection (#465)', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Tagging').click()
  await openProposalFilters(page)
  const panel = page.locator('.ai-assist-panel')
  await panel.locator('.auto-span-bulk-bar .q-checkbox').click()
  await expect(page.getByTestId('proposal-selection-count')).toContainText('1 selected')
  await page.getByTestId('proposal-tag-filter').click()
  await page.getByRole('option', { name: fixture.tag('person').name, exact: true }).click()
  await expect(page.getByTestId('no-matching-proposals')).toBeVisible()

  await openDocument(page, 'newspapers', 'chronicle')
  await sidebarPanelButton(page, 'AI Tagging').click()
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Tagging').click()
  await expect(page.getByTestId('no-matching-proposals')).toHaveCount(0)
  await expect(page.getByTestId('proposal-match-count')).toContainText('1 match')
  await expect(page.getByTestId('proposal-selection-count')).toContainText('0 selected')
  await expect(panel.getByRole('button', { name: 'Clear selection' })).toBeDisabled()
  await expect(panel.getByRole('button', { name: 'Confirm' })).toBeDisabled()
})

test('tag filter displays pictograms and confidence remains a numeric input (#465)', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Tagging').click()
  await openProposalFilters(page)
  const confidence = page.getByTestId('proposal-confidence-filter')
  await expect(confidence).toHaveAttribute('type', 'number')
  await confidence.fill('75')
  await expect(confidence).toHaveValue('75')
  await page.getByTestId('proposal-tag-filter').click()
  const place = page.getByRole('option', { name: fixture.tag('place').name, exact: true })
  await expect(place.locator('.q-icon')).toHaveCount(1)
  await place.click()

  const tagFilter = page.getByTestId('proposal-tag-filter')
  await expect(tagFilter).toContainText(fixture.tag('place').name)

  const tagField = page.locator('.q-field').filter({ has: tagFilter })
  await expect(tagField.locator('.q-field__prepend .q-icon')).toHaveCount(1)
})

test('compact filters and pending suggestions fold without losing filter state (#465)', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Tagging').click()

  await expect(page.getByTestId('proposal-sort')).toBeVisible()
  await expect(page.getByTestId('proposal-tag-filter')).toHaveCount(0)
  await openProposalFilters(page)
  await page.getByTestId('proposal-tag-filter').click()
  await page.getByRole('option', { name: fixture.tag('person').name, exact: true }).click()
  await expect(page.getByTestId('proposal-active-filters')).toHaveCount(0)
  await expect(page.getByTestId('proposal-filter-count')).toHaveText('1 active filter')
  await expect(page.getByTestId('proposal-reset-filters')).toBeEnabled()
  await expect(page.getByTestId('no-matching-proposals')).toBeVisible()

  await page.getByTestId('proposal-filters-toggle').click()
  await expect(page.getByTestId('proposal-tag-filter')).toHaveCount(0)
  await expect(page.getByTestId('proposal-active-filters')).toBeVisible()
  await page.getByTestId('pending-suggestions-toggle').click()
  await expect(page.getByTestId('proposal-sort')).toHaveCount(0)
  await page.getByTestId('pending-suggestions-toggle').click()
  await expect(page.getByTestId('proposal-active-filters')).toBeVisible()
  await page.getByTestId('proposal-filter-tag-chip').locator('.q-chip__icon--remove').click()
  await expect(page.getByTestId('proposal-match-count')).toContainText('1 match')

  await openProposalFilters(page)
  await expect(page.getByTestId('proposal-filter-count')).toHaveText('0 active filters')
  await expect(page.getByTestId('proposal-reset-filters')).toBeDisabled()
  await page.getByTestId('proposal-tag-filter').click()
  await page.getByRole('option', { name: fixture.tag('person').name, exact: true }).click()
  await page.getByTestId('proposal-reset-filters').click()
  await expect(page.getByTestId('proposal-filter-count')).toHaveText('0 active filters')
  await expect(page.getByTestId('proposal-match-count')).toContainText('1 match')
  await expect(page.locator('[data-sidebar-panel] .ai-assist-panel')).toBeVisible()
  await expect(page.locator('.sidebar-panel').filter({ has: page.locator('.ai-assist-panel') }))
    .not.toHaveClass(/sidebar-panel--fill/)
})
