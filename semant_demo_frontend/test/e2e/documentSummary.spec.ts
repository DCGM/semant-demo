import { expect, test, type Page } from '@playwright/test'
import { apiToken, chunkText, ensureLoggedIn, fixture, openDocument, sidebarPanelButton } from './support'

// Document summary as an answer in the AI Chat panel (#249, #245). The e2e profile's fake
// LLM answers "Fake summary of N passage(s); last [docN]." for the [docN]-labelled chunks it
// was sent (tests/fake_providers.py::fake_chat_answer), so the chunk count and the last
// citation are deterministic. The fixture "chronicle" document has 3 chunks in document
// order: chronicle_1, chronicle_2 (members of "chronicles"), chronicle_3 (member of
// "newspapers" only). Like the chat, the summary covers only the chunks in the collection
// (ADR 0006).

const answers = (page: Page) => page.getByTestId('chat-answer')
const summarize = (page: Page) => page.getByRole('button', { name: 'Summarize briefly' })
// The summary request with any query string (it carries the length level, #360).
const SUMMARY_URL = /\/documents\/[^/]+\/summary(\?|$)/

test('summarizing shows citations, and the AI Chat panel (switching to it, Summarize, a citation) never discards an open annotation popover', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  // chronicle_3 is the only member of "newspapers": the one passage summarized and cited.
  await openDocument(page, 'newspapers', 'chronicle')
  await expect(chunkText(page, 'chronicle_3')).toBeVisible()

  // Switching to the panel, Summarize and a citation must each leave an open popover alone
  // (DocumentReaderPage.vue's onClickOutside exempts the whole right sidebar).
  await page.locator('.gutter-item').first().click()
  const popover = page.locator('.annotation-popover')
  await expect(popover.getByRole('button', { name: 'Change tag' })).toBeVisible()

  await sidebarPanelButton(page, 'AI Chat').click()
  await expect(popover.getByRole('button', { name: 'Change tag' })).toBeVisible()

  await summarize(page).click()
  await expect(page.getByTestId('chat-question')).toHaveText('Summarize briefly')
  await expect(answers(page)).toHaveText('Fake summary of 1 passage(s); last [S1].')
  await expect(popover.getByRole('button', { name: 'Change tag' })).toBeVisible()

  await answers(page).getByRole('link', { name: '[S1]' }).click()

  await expect(chunkText(page, 'chronicle_3')).toBeInViewport()
  await expect(popover.getByRole('button', { name: 'Change tag' })).toBeVisible()
})

test('the summary covers only the chunks in the collection, and a follow-up asks about it', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Chat').click()

  await summarize(page).click()
  // chronicle_1 and chronicle_2, not chronicle_3 (only in "newspapers").
  await expect(answers(page)).toHaveText('Fake summary of 2 passage(s); last [S1].')
  await answers(page).getByRole('link', { name: '[S1]' }).click()
  await expect(chunkText(page, 'chronicle_2')).toBeInViewport()
  await expect(chunkText(page, 'chronicle_3')).toHaveCount(0)

  // The summary is an earlier answer: its cited chunk goes back as the turn's chunk id.
  const followUp = page.waitForRequest(/\/documents\/[^/]+\/chat$/)
  await page.getByLabel('Ask about this document').fill('A dál?')
  await page.getByRole('button', { name: 'Send the question' }).click()
  expect((await followUp).postDataJSON().history).toEqual([
    { role: 'user', text: 'Summarize briefly', chunk_ids: [] },
    { role: 'assistant', text: 'Fake summary of 2 passage(s); last [doc1].', chunk_ids: [fixture.chunk('chronicle_2').id] }
  ])
  await expect(answers(page)).toHaveCount(2)
})

test('a citation to a chunk outside the displayed window loads it on demand and scrolls to it', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  // In "chronicles" only chronicle_1 and chronicle_2 are displayed; chronicle_3 (order 2) is
  // not loaded. A stubbed summary cites it, so the reader must load it
  // (useChunkWindow.loadUntil, #358 review) before scrolling, not leave a dead link.
  await openDocument(page, 'chronicles', 'chronicle')
  await expect(chunkText(page, 'chronicle_1')).toBeVisible()
  await expect(chunkText(page, 'chronicle_3')).toHaveCount(0)
  await sidebarPanelButton(page, 'AI Chat').click()
  await page.route(SUMMARY_URL, (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      document_id: fixture.document('chronicle').id,
      summary: 'Later [doc2].',
      citations: [
        { chunk_id: fixture.chunk('chronicle_1').id, order: 0, from_page: 1, to_page: 1 },
        { chunk_id: fixture.chunk('chronicle_3').id, order: 2, from_page: 2, to_page: 2 }
      ],
      time_spent: 1,
      total_chunks: 2,
      summarized_chunks: 2,
      truncated: false
    })
  }))

  await summarize(page).click()
  await answers(page).getByRole('link', { name: '[S1]' }).click()

  await expect(chunkText(page, 'chronicle_1')).toBeVisible()
  await expect(chunkText(page, 'chronicle_2')).toBeVisible()
  await expect(chunkText(page, 'chronicle_3')).toBeInViewport()
})

test('the suggested questions are offered while nothing was asked', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Chat').click()
  const questions = page.getByTestId('chat-suggested-question')
  await expect(questions).toHaveText([
    'Who are the people and places mentioned, and what is their role?',
    'When and where does this take place?'
  ])

  await questions.last().click()

  await expect(page.getByTestId('chat-question')).toHaveText('When and where does this take place?')
  await expect(answers(page)).toHaveText('Fake summary of 2 passage(s); last [S1].')
  await expect(questions).toHaveCount(0)
  await expect(summarize(page)).toBeVisible()
})

test('a generation failure shows an error, not a summary that quietly used the fallback text', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Chat').click()

  // The real backend only fails like this when the LLM provider is unreachable/misconfigured
  // (not reproducible against the deterministic fake); simulate the 502 contract.
  await page.route(SUMMARY_URL, (route) => route.fulfill({
    status: 502,
    contentType: 'application/json',
    body: JSON.stringify({ detail: 'The document could not be summarized.' })
  }))

  await summarize(page).click()

  // Scoped to the panel: the sign-in notification is also role="alert".
  await expect(answers(page).getByRole('alert')).toHaveText('The document could not be summarized.')
  await expect(answers(page).getByRole('link')).toHaveCount(0)
  await expect(summarize(page)).toBeEnabled()
})

test('switching documents drops a summary of the previous one', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Chat').click()
  await summarize(page).click()
  await expect(answers(page)).toHaveCount(1)

  // "letters" is another document of the same collection.
  await openDocument(page, 'chronicles', 'letters')
  await sidebarPanelButton(page, 'AI Chat').click()

  await expect(answers(page)).toHaveCount(0)
  await expect(summarize(page)).toBeVisible()
})

test('a long summary scrolls in the conversation while Summarize and the question input stay in view', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Chat').click()

  // The fake LLM's canned reply is always short; a realistic long summary needs a stub.
  const longSummary = Array.from({ length: 30 }, (_, i) =>
    `Sentence number ${i + 1} of a long document summary, long enough that the whole thing overflows the sidebar's height [doc1].`
  ).join(' ')
  await page.route(SUMMARY_URL, (route) => route.fulfill({
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

  await summarize(page).click()
  await expect(answers(page)).toContainText('Sentence number 30')

  await expect(summarize(page)).toBeInViewport()
  await expect(page.getByLabel('Ask about this document')).toBeInViewport()
  const list = page.locator('.chat-messages')
  expect(await list.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true)
})

test('a partial summary of a long document says so', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Chat').click()
  await page.route(SUMMARY_URL, (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      document_id: fixture.document('chronicle').id,
      summary: 'Part [doc1].',
      citations: [{ chunk_id: fixture.chunk('chronicle_1').id, order: 0, from_page: 1, to_page: 1 }],
      time_spent: 1,
      total_chunks: 55,
      summarized_chunks: 40,
      truncated: true
    })
  }))

  await summarize(page).click()

  await expect(page.getByTestId('chat-coverage')).toHaveText('Based on the first 40 of 55 passages of the document.')
})

test('a user without collection read access cannot request a document summary', async ({ request }) => {
  const response = await request.post(
    `/api/user_collections/${fixture.collection('chronicles').id}/documents/${fixture.document('chronicle').id}/summary`,
    { headers: { Authorization: `Bearer ${await apiToken(request, 'outsider')}` } }
  )

  // ADR 0007: a collection the user cannot read answers "not found", not "forbidden".
  expect(response.status()).toBe(404)
})

test('Summarize in detail sends the detailed length level (#360)', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Chat').click()

  const request = page.waitForRequest(SUMMARY_URL)
  await page.getByRole('button', { name: 'Summarize in detail' }).click()

  expect(new URL((await request).url()).searchParams.get('length')).toBe('detailed')
  await expect(page.getByTestId('chat-question')).toHaveText('Summarize in detail')
  await expect(answers(page)).toHaveText('Fake summary of 2 passage(s); last [S1].')
})
