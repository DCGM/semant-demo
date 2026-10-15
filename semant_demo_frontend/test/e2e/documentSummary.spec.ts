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

test('summarizing shows citations, and a citation to a displayed chunk scrolls to it, preserving an open annotation popover', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  // chronicle_3 (order 2, the last of the 3 chunks) is the only member of "newspapers",
  // so it is the chunk already displayed and also the one the fake always cites last.
  await openDocument(page, 'newspapers', 'chronicle')
  await expect(chunkText(page, 'chronicle_3')).toBeVisible()

  // Switch to the Summary panel and generate the summary *before* opening the popover:
  // switching sidebar panels is itself an "outside click" that already ends any in-progress
  // quick-tagging (pre-existing, general behavior — not special-cased for this panel), so the
  // popover must be opened while the Summary panel is already the active one for this test to
  // isolate what the citation click itself does.
  await sidebarPanelButton(page, 'Summary').click()
  await page.getByRole('button', { name: 'Summarize Document' }).click()
  await expect(summary(page)).toContainText('Fake summary of 3 passage(s); last [3].')

  // Open the annotation popover of the fixture span on this chunk.
  await page.locator('.gutter-item').first().click()
  const popover = page.locator('.annotation-popover')
  await expect(popover.getByRole('button', { name: 'Change tag' })).toBeVisible()

  await summary(page).getByRole('link', { name: '[3]' }).click()

  // A read-only navigation action: the chunk is (still) in view and the popover opened
  // before the click is untouched — no selection clearing, no popover changes.
  await expect(chunkText(page, 'chronicle_3')).toBeInViewport()
  await expect(popover.getByRole('button', { name: 'Change tag' })).toBeVisible()
})

test('a citation to a chunk outside the displayed window is a documented no-op', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  // In "chronicles", only chronicle_1 and chronicle_2 (order 0, 1) are members and
  // displayed by default; chronicle_3 (order 2) is not loaded. The summary still covers
  // all 3 chunks of the document, so its last citation ([doc3]) targets a chunk the reader
  // is not currently showing.
  await openDocument(page, 'chronicles', 'chronicle')
  await expect(chunkText(page, 'chronicle_1')).toBeVisible()
  await expect(chunkText(page, 'chronicle_3')).toHaveCount(0)

  await sidebarPanelButton(page, 'Summary').click()
  await page.getByRole('button', { name: 'Summarize Document' }).click()
  await expect(summary(page)).toContainText('Fake summary of 3 passage(s); last [3].')

  await summary(page).getByRole('link', { name: '[3]' }).click()

  // No crash, no chunk fetched into view: the reader's displayed window is unchanged.
  await expect(chunkText(page, 'chronicle_1')).toBeVisible()
  await expect(chunkText(page, 'chronicle_2')).toBeVisible()
  await expect(chunkText(page, 'chronicle_3')).toHaveCount(0)
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

test('a user without collection read access cannot request a document summary', async ({ request }) => {
  const response = await request.post(
    `/api/user_collections/${fixture.collection('chronicles').id}/documents/${fixture.document('chronicle').id}/summary`,
    { headers: { Authorization: `Bearer ${await apiToken(request, 'outsider')}` } }
  )

  // ADR 0007: a collection the user cannot read answers "not found", not "forbidden".
  expect(response.status()).toBe(404)
})
