import { expect, test, type Page } from '@playwright/test'
import { apiToken, chunkText, ensureLoggedIn, fixture, openDocument, sidebarPanelButton } from './support'

// Document chat in the right sidebar (#248, ADR 0012). The e2e profile's fake LLM answers
// "Fake summary of N passage(s); last [docN]." for the [docN]-labelled passages of the last
// user message (tests/fake_providers.py::fake_chat_answer). The fixture "chronicle" document
// has 3 chunks: chronicle_1 and chronicle_2 are in "chronicles", chronicle_3 only in
// "newspapers". Unlike the document summary, the chat uses only the chunks in the collection.

const CHAT_URL = /\/documents\/[^/]+\/chat$/
const answers = (page: Page) => page.getByTestId('chat-answer')

async function ask (page: Page, question: string) {
  await page.getByLabel('Ask about this document').fill(question)
  await page.getByRole('button', { name: 'Send the question' }).click()
}

test('an answer cites only the chunks in the collection, and a citation scrolls the reader without closing an open annotation', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'newspapers', 'chronicle')
  await expect(chunkText(page, 'chronicle_3')).toBeVisible()
  await page.locator('.gutter-item').first().click()
  const popover = page.locator('.annotation-popover')
  await expect(popover.getByRole('button', { name: 'Change tag' })).toBeVisible()

  await sidebarPanelButton(page, 'AI Chat').click()
  await ask(page, 'Co se stalo v obci?')

  // Only chronicle_3 is in "newspapers": one passage.
  await expect(answers(page)).toHaveText('Fake summary of 1 passage(s); last [S1].')
  await expect(page.getByTestId('chat-coverage')).toHaveCount(0)
  await answers(page).getByRole('link', { name: '[S1]' }).click()

  await expect(chunkText(page, 'chronicle_3')).toBeInViewport()
  await expect(popover.getByRole('button', { name: 'Change tag' })).toBeVisible()
})

test('a follow-up sends the earlier turns with their cited chunk ids, never source text, and keeps the S labels', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Chat').click()

  await ask(page, 'O čem je dokument?')
  // chronicle_1 and chronicle_2, not chronicle_3: [doc2] is chronicle_2.
  await expect(answers(page)).toHaveText('Fake summary of 2 passage(s); last [S1].')

  const request = page.waitForRequest(CHAT_URL)
  await ask(page, 'A dál?')
  const body = (await request).postDataJSON()

  expect(body).toEqual({
    question: 'A dál?',
    history: [
      { role: 'user', text: 'O čem je dokument?', chunk_ids: [] },
      { role: 'assistant', text: 'Fake summary of 2 passage(s); last [doc1].', chunk_ids: [fixture.chunk('chronicle_2').id] }
    ]
  })
  await expect(answers(page).nth(1)).toHaveText('Fake summary of 2 passage(s); last [S1].')

  await answers(page).nth(1).getByRole('link', { name: '[S1]' }).click()
  await expect(chunkText(page, 'chronicle_2')).toBeInViewport()

  await page.getByTestId('chat-new-conversation').click()
  await expect(answers(page)).toHaveCount(0)
})

test('switching documents starts an empty conversation and clears the typed question', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Chat').click()
  await ask(page, 'O čem je dokument?')
  await expect(answers(page)).toHaveCount(1)
  // A question typed but not sent is not carried over to the other document.
  await page.getByLabel('Ask about this document').fill('Nedokončená otázka')

  await openDocument(page, 'chronicles', 'letters')
  await sidebarPanelButton(page, 'AI Chat').click()

  await expect(page.getByTestId('chat-question')).toHaveCount(0)
  await expect(answers(page)).toHaveCount(0)
  await expect(page.getByLabel('Ask about this document')).toHaveValue('')
})

test('a user without collection read access cannot chat about its document', async ({ request }) => {
  const response = await request.post(
    `/api/user_collections/${fixture.collection('chronicles').id}/documents/${fixture.document('chronicle').id}/chat`,
    {
      headers: { Authorization: `Bearer ${await apiToken(request, 'outsider')}` },
      data: { question: 'O čem je dokument?', history: [] }
    }
  )

  // ADR 0007: a collection the user cannot read answers "not found", not "forbidden".
  expect(response.status()).toBe(404)
})
