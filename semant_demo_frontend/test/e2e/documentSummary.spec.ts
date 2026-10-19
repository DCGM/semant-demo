import { expect, test } from '@playwright/test'
import { apiToken, chunkText, ensureLoggedIn, fixture, openDocument, sidebarPanelButton } from './support'

// Document summary in the unified sidebar (#249). The e2e profile's fake Ollama answers
// "Fake summary of N passage(s); last [docN]." for the [docN]-labelled chunks it was sent
// (tests/fake_providers.py::fake_chat_answer), so the document's chunk count and the last
// citation are both deterministic. The fixture "chronicle" document has 3 chunks in document
// order: chronicle_1, chronicle_2 (members of "chronicles"), chronicle_3 (member of
// "newspapers" only) — the summary always covers all 3 regardless of which collection it is
// requested from (read_chunks_in_collection returns the whole document), but the reader only
// *displays* a collection's member chunks by default.

const summary = (page: import('@playwright/test').Page) => page.getByTestId('document-summary')

test('summarizing shows citations, and interacting with the summary sidebar (switching to it, Summarize, a citation) never discards an open annotation popover', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  // chronicle_3 (order 2, the last of the 3 chunks) is the only member of "newspapers",
  // so it is the chunk already displayed and also the one the fake always cites last.
  await openDocument(page, 'newspapers', 'chronicle')
  await expect(chunkText(page, 'chronicle_3')).toBeVisible()

  // Open the annotation popover of the fixture span on this chunk *before* touching the
  // Summary panel at all, mirroring review feedback: switching to the Summary panel,
  // clicking Summarize, and clicking a citation must each leave an open popover alone — none of them are "outside" the editing
  // context, even though the document-level click-outside handler would otherwise treat
  // them that way (DocumentReaderPage.vue's onClickOutside exempts the whole right sidebar).
  await page.locator('.gutter-item').first().click()
  const popover = page.locator('.annotation-popover')
  await expect(popover.getByRole('button', { name: 'Change tag' })).toBeVisible()

  await sidebarPanelButton(page, 'Summary').click()
  await expect(popover.getByRole('button', { name: 'Change tag' })).toBeVisible()

  await page.getByRole('button', { name: 'Summarize Document' }).click()
  await expect(summary(page)).toContainText('Fake summary of 3 passage(s); last [3].')
  await expect(popover.getByRole('button', { name: 'Change tag' })).toBeVisible()

  await summary(page).getByRole('link', { name: '[3]' }).click()

  // A read-only navigation action: the chunk is (still) in view and the popover opened
  // before any of this is still untouched — no selection clearing, no popover changes.
  await expect(chunkText(page, 'chronicle_3')).toBeInViewport()
  await expect(popover.getByRole('button', { name: 'Change tag' })).toBeVisible()
})

test('a citation to a chunk outside the displayed window loads it on demand and scrolls to it', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  // In "chronicles", only chronicle_1 and chronicle_2 (order 0, 1) are members and
  // displayed by default; chronicle_3 (order 2) is not loaded. The summary still covers
  // all 3 chunks of the document, so its last citation ([doc3]) targets a chunk the reader
  // is not currently showing — useChunkWindow.loadUntil must load it (#358 review) rather
  // than leaving the citation a silent dead link.
  await openDocument(page, 'chronicles', 'chronicle')
  await expect(chunkText(page, 'chronicle_1')).toBeVisible()
  await expect(chunkText(page, 'chronicle_3')).toHaveCount(0)

  await sidebarPanelButton(page, 'Summary').click()
  await page.getByRole('button', { name: 'Summarize Document' }).click()
  await expect(summary(page)).toContainText('Fake summary of 3 passage(s); last [3].')

  await summary(page).getByRole('link', { name: '[3]' }).click()

  // The previously-unloaded chunk is now displayed and scrolled into view; the chunks
  // already shown are unaffected.
  await expect(chunkText(page, 'chronicle_1')).toBeVisible()
  await expect(chunkText(page, 'chronicle_2')).toBeVisible()
  await expect(chunkText(page, 'chronicle_3')).toBeVisible()
  await expect(chunkText(page, 'chronicle_3')).toBeInViewport()
})

test('a generation failure shows an error, not a summary that quietly used the fallback text', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'Summary').click()

  // The real backend only fails like this when the LLM provider is unreachable/misconfigured
  // (not reproducible against the deterministic fake); simulate the 502 contract at the
  // network layer to verify the panel shows it as an error, not a successful summary card.
  await page.route('**/documents/*/summary', (route) => route.fulfill({
    status: 502,
    contentType: 'application/json',
    body: JSON.stringify({ detail: 'The document could not be summarized.' })
  }))

  await page.getByRole('button', { name: 'Summarize Document' }).click()

  // Scoped to the panel: the sign-in notification is also role="alert".
  await expect(page.locator('.document-summary-panel').getByRole('alert')).toHaveText('The document could not be summarized.')
  await expect(summary(page)).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Summarize Document' })).toBeVisible()
})

test('switching documents drops a summary of the previous one', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'Summary').click()
  await page.getByRole('button', { name: 'Summarize Document' }).click()
  await expect(summary(page)).toBeVisible()

  // "letters" is another document of the same collection.
  await openDocument(page, 'chronicles', 'letters')
  await sidebarPanelButton(page, 'Summary').click()

  await expect(summary(page)).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Summarize Document' })).toBeVisible()
})

test('a long summary stays below the Summarize button, scrolling on its own, instead of wrapping beside it', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'Summary').click()

  // The fake LLM's canned reply is always short, so a long, realistic summary (one that
  // overflows the sidebar's fixed "fill" height) needs a stubbed response: this exact shape
  // regressed once (#358) into wrapping sideways next to the button instead of scrolling
  // below it, because the panel's root inherited Quasar's .column default flex-wrap.
  const longSummary = Array.from({ length: 20 }, (_, i) =>
    `Sentence number ${i + 1} of a long document summary, long enough that the whole thing overflows the sidebar's height [doc1].`
  ).join(' ')
  await page.route('**/documents/*/summary', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      document_id: fixture.document('chronicle').id,
      summary: longSummary,
      citations: [{ chunk_id: fixture.chunk('chronicle_1').id, order: 0, from_page: 1, to_page: 1 }],
      time_spent: 1,
      total_chunks: 1,
      summarized_chunks: 1,
      truncated: false
    })
  }))

  const summarizeButton = page.getByRole('button', { name: 'Summarize Document' })
  await summarizeButton.click()
  await expect(summary(page)).toBeVisible()

  const buttonBox = await summarizeButton.boundingBox()
  const summaryBox = await summary(page).boundingBox()
  if (!buttonBox || !summaryBox) throw new Error('expected both the button and the summary card to have a layout box')

  // Stacked (the card starts at or below the button's bottom), not side by side.
  expect(summaryBox.y).toBeGreaterThanOrEqual(buttonBox.y + buttonBox.height - 1)
  // Same column (the card doesn't start to the right of the button).
  expect(summaryBox.x).toBeLessThanOrEqual(buttonBox.x + 1)
})

test('a user without collection read access cannot request a document summary', async ({ request }) => {
  const response = await request.post(
    `/api/user_collections/${fixture.collection('chronicles').id}/documents/${fixture.document('chronicle').id}/summary`,
    { headers: { Authorization: `Bearer ${await apiToken(request, 'outsider')}` } }
  )

  // ADR 0007: a collection the user cannot read answers "not found", not "forbidden".
  expect(response.status()).toBe(404)
})
