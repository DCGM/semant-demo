import { expect, test, type Page } from '@playwright/test'
import { ensureLoggedIn, search } from './support'

// App-level right sidebar with the Search page's AI Chat panel, where summaries are answers of
// the conversation (#245). The e2e profile's fake LLM answers "Fake summary of N passage(s);
// last [docN]." for the passages it was sent, so the cited result shows which results were
// summarized.

const answers = (page: Page) => page.getByTestId('chat-answer')

test('a search summary in AI Chat works on the selected results only', async ({ page }) => {
  await page.goto('/#/search')
  const sidebarToggle = page.getByRole('button', { name: 'Toggle sidebar' })
  await expect(sidebarToggle).toHaveCount(0) // no panel before there are results

  await page.getByRole('combobox', { name: 'Search query' }).fill('Lhota')
  await page.keyboard.press('Enter')
  await expect(page.locator('#result-2')).toBeVisible()
  await expect(sidebarToggle).toBeVisible()
  await expect(page.getByRole('listitem', { name: 'AI Chat' })).toBeVisible()

  // Select the second result only: the chat's scope, and so the summary's, is that result.
  await page.locator('#result-2 .q-checkbox').click()
  await expect(page.getByTestId('chat-scope')).toHaveText('Asking about 1 selected result')
  await page.getByRole('button', { name: 'Summarize briefly' }).click()

  await expect(page.getByTestId('chat-question')).toHaveText('Summarize briefly')
  await expect(answers(page)).toHaveText('Fake summary of 1 passage(s); last [S1].')
  await answers(page).getByRole('link', { name: '[S1]' }).click()
  await expect(page.locator('#result-2')).toHaveClass(/citation-target-highlight/)

  // A new search is a new scope: the summary stays with a notice until the next question.
  await page.getByRole('combobox', { name: 'Search query' }).fill('Brno')
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('chat-scope-changed')).toBeVisible()
})

test('suggested messages: Summarize in detail sends the length (#360), questions go once something was asked, and a follow-up asks about the summary', async ({ page }) => {
  await search(page, 'Lhota')
  const questions = page.getByTestId('chat-suggested-question')
  await expect(questions).toHaveCount(2)

  const request = page.waitForRequest((r) => r.url().includes('/api/summarize/results'))
  await page.getByRole('button', { name: 'Summarize in detail' }).click()

  expect(new URL((await request).url()).searchParams.get('length')).toBe('detailed')
  await expect(page.getByTestId('chat-question')).toHaveText('Summarize in detail')
  await expect(answers(page)).toContainText('Fake summary of')
  // The summaries stay; the suggested questions are for an empty conversation.
  await expect(questions).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Summarize briefly' })).toBeVisible()

  // The summary is an earlier answer: its cited result goes back as the turn's chunk id, not as text.
  const followUp = page.waitForRequest(/\/api\/search\/chat$/)
  await page.getByLabel('Ask about these results').fill('Proč?')
  await page.getByRole('button', { name: 'Send the question' }).click()
  const body = (await followUp).postDataJSON()
  expect(body.history).toHaveLength(2)
  expect(body.history[0]).toEqual({ role: 'user', text: 'Summarize in detail', chunk_ids: [] })
  expect(body.history[1].chunk_ids).toHaveLength(1)
  expect(body.history[1].chunk_ids[0]).toBe(body.chunk_ids[body.chunk_ids.length - 1])
  await expect(answers(page)).toHaveCount(2)

  // New conversation: the suggested questions are back, and one is asked as it reads.
  await page.getByTestId('chat-new-conversation').click()
  await expect(questions).toHaveCount(2)
  const asked = page.waitForRequest(/\/api\/search\/chat$/)
  await questions.first().click()
  expect((await asked).postDataJSON().question).toBe('What do these results have in common?')
})

test('a failed search summary is shown as an error and not sent back as history', async ({ page }) => {
  await search(page, 'Lhota')
  // The route answers 200 with the configured fallback text when generation fails.
  await page.route((url) => url.pathname.endsWith('/api/summarize/results'), (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ summary: 'The summary could not be generated.', time_spent: 0.1, failed: true })
  }))

  await page.getByRole('button', { name: 'Summarize briefly' }).click()
  await expect(answers(page).getByRole('alert')).toHaveText('The summary could not be generated.')

  const followUp = page.waitForRequest(/\/api\/search\/chat$/)
  await page.getByLabel('Ask about these results').fill('Proč?')
  await page.getByRole('button', { name: 'Send the question' }).click()
  expect((await followUp).postDataJSON().history).toEqual([])
})

test('the sidebar goes away with the page that registered its panel', async ({ page }) => {
  await ensureLoggedIn(page, 'owner') // Collections is in the navigation of signed-in users only
  await search(page, 'Lhota')
  await expect(page.getByRole('button', { name: 'Toggle sidebar' })).toBeVisible()

  await page.locator('.q-drawer').getByText('Collections', { exact: true }).click()

  await expect(page.getByRole('button', { name: 'Toggle sidebar' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Summarize briefly' })).toHaveCount(0)
})
