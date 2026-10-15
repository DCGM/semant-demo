import { expect, test, type Page } from '@playwright/test'

import { answerChat, askChat, chatSource, closePhoneNavigation, fixture, sidebarPanelButton, useViewport } from './support'

// The chat assistant's sources in the right sidebar (#246): the Sources panel lists the
// sources of the clicked answer, the Document panel shows one of them highlighted in its
// document (the same viewer as a search result's context, #244).

const chronicle = fixture.document('chronicle')
const gazette = fixture.document('gazette')

const sourcesPanel = (page: Page) => page.getByTestId('chat-sources')
const documentPanel = (page: Page) => page.getByTestId('chunk-context')
const match = (page: Page) => documentPanel(page).locator('[aria-current="true"]')
const title = (page: Page) => page.getByTestId('right-sidebar-title')
const answer = (page: Page, text: string) => page.locator('.message-bubble', { hasText: text })

async function openChat (page: Page) {
  await page.goto('/#/rag')
  await closePhoneNavigation(page)
}

const twoAnswers = [
  { rag_answer: 'The chronicle tells of a fire [doc 2].', sources: [chatSource('chronicle_1'), chatSource('chronicle_3')] },
  { rag_answer: 'The gazette describes a café [doc 1] and a market [doc 2].', sources: [chatSource('gazette_1'), chatSource('gazette_2')] }
]

test("each answer's sources and citations show that answer's sources", async ({ page }) => {
  await useViewport(page, 'narrow')
  await answerChat(page, twoAnswers)
  await openChat(page)
  // No sources, no sidebar.
  await expect(page.getByRole('button', { name: 'Toggle sidebar' })).toHaveCount(0)
  await askChat(page, 'What happened in Lhota?')
  await askChat(page, 'What is in the gazette?')
  const scrollBefore = await page.evaluate(() => window.scrollY)

  // The first (not the latest) answer's sources.
  await answer(page, 'The chronicle tells').getByText('Sources', { exact: true }).click()
  await expect(title(page)).toHaveText('Sources')
  await expect(sourcesPanel(page)).toContainText('What happened in Lhota?')
  const items = sourcesPanel(page).getByRole('listitem')
  await expect(items).toHaveCount(2)
  await expect(items.nth(0)).toContainText(fixture.chunk('chronicle_1').text)
  await expect(items.nth(1)).toContainText(fixture.chunk('chronicle_3').text)
  await expect(items.nth(0)).toContainText(chronicle.properties.title)
  await expect(sidebarPanelButton(page, 'Document')).toHaveCount(0)
  // Beside the chat, not over it: no close button of the overlay.
  await expect(page.getByRole('button', { name: 'Close sidebar' })).toHaveCount(0)

  // A source opens highlighted in its document.
  await items.nth(1).getByRole('button', { name: 'View source doc 2 in its document' }).click()
  await expect(title(page)).toHaveText('Document')
  await expect(match(page)).toHaveText(fixture.chunk('chronicle_3').text)
  await expect(documentPanel(page).getByTestId('chunk-context-header')).toContainText(chronicle.properties.title)
  await expect(documentPanel(page).locator('.chunk-context__chunk')).toHaveCount(3)

  // A citation of the second answer switches to that answer's sources; nothing of the
  // first answer stays.
  await answer(page, 'The gazette describes').getByRole('link', { name: '[doc 2]' }).click()
  await expect(title(page)).toHaveText('Document')
  await expect(match(page)).toHaveText(fixture.chunk('gazette_2').text)
  await expect(documentPanel(page)).not.toContainText(chronicle.properties.title)
  await expect(answer(page, 'The gazette describes').getByRole('link', { name: '[doc 2]' })).toHaveAttribute('aria-current', 'true')
  await sidebarPanelButton(page, 'Sources').click()
  await expect(sourcesPanel(page)).toContainText('What is in the gazette?')
  await expect(items.nth(0)).toContainText(fixture.chunk('gazette_1').text)
  await expect(items.nth(1)).toHaveAttribute('aria-current', 'true')

  // Showing another answer's sources closes the open source of the previous one.
  await answer(page, 'The chronicle tells').getByText('Sources', { exact: true }).click()
  await expect(sourcesPanel(page)).toContainText('What happened in Lhota?')
  await expect(sidebarPanelButton(page, 'Document')).toHaveCount(0)

  // The conversation did not move.
  expect(await page.evaluate(() => window.scrollY)).toBe(scrollBefore)
})

test('Focus on source brings the cited passage back; resetting the chat closes the sources', async ({ page }) => {
  await useViewport(page, 'narrow')
  await answerChat(page, twoAnswers)
  await openChat(page)
  await askChat(page, 'What happened in Lhota?')

  await answer(page, 'The chronicle tells').getByRole('link', { name: '[doc 2]' }).click()
  await expect(match(page)).toHaveText(fixture.chunk('chronicle_3').text)
  await documentPanel(page).locator('.chunk-context__chunk').first().scrollIntoViewIfNeeded()
  await documentPanel(page).getByRole('button', { name: 'Focus on source' }).click()
  await expect(match(page)).toBeInViewport()

  await page.getByTitle('Reset chat').click()
  await expect(page.getByRole('button', { name: 'Toggle sidebar' })).toHaveCount(0)
  await expect(page.locator('.q-drawer--right')).toBeHidden()
  await expect(answer(page, 'The chronicle tells')).toHaveCount(0)

  // A new conversation starts without sources; its answers show their own.
  await askChat(page, 'What is in the gazette?')
  await answer(page, 'The gazette describes').getByRole('link', { name: '[doc 1]' }).click()
  await expect(match(page)).toHaveText(fixture.chunk('gazette_1').text)
  await expect(documentPanel(page)).toContainText(gazette.properties.title)
})

test('a source that is no longer stored is reported, not replaced', async ({ page }) => {
  await useViewport(page, 'narrow')
  const missing = { ...chatSource('chronicle_2'), id: '5e3a0000-0000-4000-8000-0000000d1fff' }
  await answerChat(page, [{ rag_answer: 'An answer from a removed passage [doc 1].', sources: [missing] }])
  await openChat(page)
  await askChat(page, 'Question')

  await answer(page, 'An answer from a removed').getByRole('link', { name: '[doc 1]' }).click()
  await expect(documentPanel(page).getByRole('alert')).toContainText('no longer available')
  await expect(documentPanel(page).locator('.chunk-context__chunk')).toHaveCount(0)
  // The source's own excerpt stays available.
  await sidebarPanelButton(page, 'Sources').click()
  await expect(sourcesPanel(page)).toContainText(fixture.chunk('chronicle_2').text)
})

test('a citation in an explanation opens the source beside the chat', async ({ page }) => {
  await useViewport(page, 'narrow')
  await answerChat(page, [twoAnswers[0]])
  await page.route('**/api/rag/explain', (route) => route.fulfill({ json: { explanation: 'It is stated in [doc 1].' } }))
  await openChat(page)
  await askChat(page, 'What happened in Lhota?')

  const text = answer(page, 'The chronicle tells').locator('.markdown-body')
  await text.selectText()
  await text.dispatchEvent('mouseup')
  await page.getByRole('button', { name: 'Explain' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('link', { name: '[doc 1]' }).click()

  await expect(dialog).toHaveCount(0)
  await expect(match(page)).toHaveText(fixture.chunk('chronicle_1').text)
})

test('on a phone the sources are an overlay over the chat', async ({ page }) => {
  await useViewport(page, 'phone')
  await answerChat(page, [twoAnswers[0]])
  await openChat(page)
  await askChat(page, 'What happened in Lhota?')

  await answer(page, 'The chronicle tells').getByRole('link', { name: '[doc 2]' }).click()
  await expect(match(page)).toBeInViewport()
  // The source fits the phone without horizontal scrolling.
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)

  await sidebarPanelButton(page, 'Sources').click()
  await expect(sourcesPanel(page).getByRole('listitem').first()).toBeInViewport()
  // The overlay covers the header's toggle; its own button returns to the chat.
  await page.getByRole('button', { name: 'Close sidebar' }).click()
  await expect(page.locator('.q-drawer--right')).toBeHidden()
  await expect(answer(page, 'The chronicle tells')).toBeInViewport()
})
