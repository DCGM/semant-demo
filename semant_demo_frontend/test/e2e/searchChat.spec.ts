import { expect, test, type Page } from '@playwright/test'
import { search, sidebarPanelButton, useViewport } from './support'

// Search chat in the right sidebar (#245, ADR 0012): about the selected results, or all
// loaded ones. The e2e profile's fake LLM answers "Fake summary of N passage(s); last
// [docN]." for the [docN]-labelled passages of the last user message
// (tests/fake_providers.py::fake_chat_answer), so N is the number of results asked about and
// the citation is the last of them.

const CHAT_URL = /\/api\/search\/chat$/
const answers = (page: Page) => page.getByTestId('chat-answer')
const scope = (page: Page) => page.getByTestId('chat-scope')
const notice = (page: Page) => page.getByTestId('chat-scope-changed')

async function ask (page: Page, question: string) {
  await page.getByLabel('Ask about these results').fill(question)
  await page.getByRole('button', { name: 'Send the question' }).click()
}

test('a signed-out user asks about all loaded results, and a citation shows its result in the Document panel', async ({ page }) => {
  await useViewport(page, 'narrow')
  await search(page, 'Lhota')
  const count = await page.locator('.search-result').count()
  // Summary stays the default panel.
  await expect(page.getByTestId('right-sidebar-title')).toHaveText('Summary')

  await sidebarPanelButton(page, 'Chat').click()
  await expect(scope(page)).toHaveText(count === 1 ? 'Asking about the one loaded result' : `Asking about all ${count} loaded results`)
  const request = page.waitForRequest(CHAT_URL)
  await ask(page, 'Co se stalo v Lhotě?')

  const body = (await request).postDataJSON()
  expect(body.chunk_ids).toHaveLength(count)
  expect(body.criteria.text_query).toBe('Lhota')
  expect(body).not.toHaveProperty('sources')
  await expect(answers(page)).toHaveText(`Fake summary of ${count} passage(s); last [S1].`)

  // The last result asked about is cited; the click opens it without selecting it.
  await answers(page).getByRole('link', { name: '[S1]' }).click()
  await expect(page.getByTestId('right-sidebar-title')).toHaveText('Document')
  const cited = page.locator(`#result-${count}`)
  await expect(cited).toHaveClass(/citation-target-highlight/)
  await expect(cited.getByRole('checkbox')).toHaveAttribute('aria-checked', 'false')
})

test('selecting results is a new scope: the old conversation stays with a notice until the next question', async ({ page }) => {
  await useViewport(page, 'narrow')
  await search(page, 'Lhota')
  await sidebarPanelButton(page, 'Chat').click()
  await ask(page, 'O čem jsou výsledky?')
  await expect(answers(page)).toHaveCount(1)
  await expect(notice(page)).toHaveCount(0)

  await page.locator('#result-1').getByRole('checkbox').click()
  await page.locator('#result-2').getByRole('checkbox').click()

  await expect(scope(page)).toHaveText('Asking about 2 selected results')
  await expect(notice(page)).toContainText('Your next question starts a new conversation, about 2 selected results.')
  await expect(answers(page)).toHaveCount(1)

  const request = page.waitForRequest(CHAT_URL)
  await ask(page, 'A tyto dva?')
  const body = (await request).postDataJSON()

  expect(body.history).toEqual([])
  expect(body.chunk_ids).toHaveLength(2)
  await expect(answers(page)).toHaveText('Fake summary of 2 passage(s); last [S1].')
  await expect(page.getByTestId('chat-question')).toHaveText('A tyto dva?')
  await expect(notice(page)).toHaveCount(0)
})
