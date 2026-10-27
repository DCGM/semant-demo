import { expect, test, type Page } from '@playwright/test'

import { answerChat, askChat, chatSource, closePhoneNavigation, fixture, sidebarPanelButton, useViewport } from './support'

// The chat assistant's sources in the right sidebar (#246): the Sources panel lists every
// source chunk of the conversation once, labelled S1, S2... as the citations in the answers;
// one click selects (and expands) a source, a double click opens it highlighted in its
// document (the same viewer as a search result's context, #244).

const chronicle = fixture.document('chronicle')
const gazette = fixture.document('gazette')
const text = (key: string) => fixture.chunk(key).text

const sourcesPanel = (page: Page) => page.getByTestId('chat-sources')
const sourceItem = (page: Page, label: string) => sourcesPanel(page).getByRole('listitem', { name: `Source ${label}`, exact: true })
const sourceSummary = (page: Page, label: string) => sourceItem(page, label).locator('.chat-sources__summary')
const documentPanel = (page: Page) => page.getByTestId('chunk-context')
const match = (page: Page) => documentPanel(page).locator('[aria-current="true"]')
const title = (page: Page) => page.getByTestId('right-sidebar-title')
const answer = (page: Page, start: string) => page.locator('.message-bubble', { hasText: start })
const citations = (page: Page, label: string) => page.locator('.message-bubble').getByRole('link', { name: `[${label}]`, exact: true })
const selectedCitations = (page: Page) => page.locator('.message-bubble a.source-link[aria-current="true"]')
const scrollY = (page: Page) => page.evaluate(() => window.scrollY)

async function openChat (page: Page) {
  await page.goto('/#/rag')
  await closePhoneNavigation(page)
}

// Answer 1 cites its doc 2 twice; answer 2 cites the same chunk (its own doc 2) again and a
// doc 7 it has no source for.
const answers = [
  {
    rag_answer: 'A fire [doc 2] after the arrival [doc 1]; the fire again [doc 2].',
    sources: [chatSource('chronicle_1'), chatSource('chronicle_3')]
  },
  {
    rag_answer: 'The gazette has a café [doc 1], the same fire [doc 2] and more [doc 7].',
    sources: [chatSource('gazette_1'), chatSource('chronicle_3')]
  }
]

async function askBoth (page: Page) {
  await answerChat(page, answers)
  await openChat(page)
  await askChat(page, 'What happened in Lhota?')
  await askChat(page, 'What is in the gazette?')
}

test('the sources of the whole conversation are listed once, with stable labels', async ({ page }) => {
  await useViewport(page, 'narrow')
  await answerChat(page, answers)
  await openChat(page)
  // No sources, no sidebar.
  await expect(page.getByRole('button', { name: 'Toggle sidebar' })).toHaveCount(0)
  await askChat(page, 'What happened in Lhota?')
  await expect(citations(page, 'S2')).toHaveCount(2)
  await expect(citations(page, 'S1')).toHaveCount(1)

  await askChat(page, 'What is in the gazette?')
  // The chunk cited again keeps S2; the new one is S3; doc 7 has no source and stays as written.
  await expect(answer(page, 'The gazette has')).toContainText('a café [S3], the same fire [S2] and more [doc 7].')
  await expect(answer(page, 'The gazette has').locator('.markdown-body').getByRole('link')).toHaveCount(2)
  await expect(citations(page, 'S2')).toHaveCount(3)
  await expect(answer(page, 'A fire')).toContainText('A fire [S2] after the arrival [S1]; the fire again [S2].')

  await expect(title(page)).toHaveText('Sources')
  await expect(sourcesPanel(page).getByRole('listitem')).toHaveText([
    new RegExp(`^S1.*${chronicle.properties.title}.*${text('chronicle_1')}`),
    new RegExp(`^S2.*${chronicle.properties.title}.*${text('chronicle_3')}`),
    new RegExp(`^S3.*${gazette.properties.title}.*${text('gazette_1')}`)
  ])
  // Beside the chat, not over it: no close button of the overlay.
  await expect(page.getByRole('button', { name: 'Close sidebar' })).toHaveCount(0)
})

test('one click selects a source from either surface and marks all its citations', async ({ page }) => {
  await useViewport(page, 'narrow')
  await askBoth(page)
  const scrollBefore = await scrollY(page)

  // A citation in the second answer selects S2 and expands it in the list.
  await answer(page, 'The gazette has').getByRole('link', { name: '[S2]' }).click()
  await expect(title(page)).toHaveText('Sources')
  await expect(sourceItem(page, 'S2')).toHaveAttribute('aria-current', 'true')
  await expect(sourceSummary(page, 'S2')).toHaveAttribute('aria-expanded', 'true')
  await expect(sourceSummary(page, 'S1')).toHaveAttribute('aria-expanded', 'false')
  await expect(sourceItem(page, 'S2')).toBeInViewport()
  // Every citation of S2, in both answers, and nothing else.
  await expect(selectedCitations(page)).toHaveText(['[S2]', '[S2]', '[S2]'])

  // Selecting in the list moves the marks; the previous source collapses.
  await sourceSummary(page, 'S1').click()
  await expect(sourceSummary(page, 'S1')).toHaveAttribute('aria-expanded', 'true')
  await expect(sourceSummary(page, 'S2')).toHaveAttribute('aria-expanded', 'false')
  await expect(selectedCitations(page)).toHaveText(['[S1]'])
  // Clicking the active source keeps it expanded.
  await sourceSummary(page, 'S1').click()
  await expect(sourceSummary(page, 'S1')).toHaveAttribute('aria-expanded', 'true')

  // The conversation did not move.
  expect(await scrollY(page)).toBe(scrollBefore)
})

test('the selected source shows its full stored text', async ({ page }) => {
  await useViewport(page, 'narrow')
  const long = Array.from({ length: 40 }, (_, i) => `Sentence ${i + 1} of a long passage.`).join(' ')
  await answerChat(page, [{ rag_answer: 'Long [doc 1], short [doc 2].', sources: [{ ...chatSource('chronicle_1'), text: long }, chatSource('chronicle_3')] }])
  await openChat(page)
  await askChat(page, 'Question')

  const fullText = sourceItem(page, 'S1').getByTestId('chat-source-text')
  await expect(fullText).toBeVisible()
  const collapsed = (await fullText.boundingBox())!.height
  await citations(page, 'S1').click()
  await expect(sourceSummary(page, 'S1')).toHaveAttribute('aria-expanded', 'true')
  await expect.poll(async () => (await fullText.boundingBox())!.height).toBeGreaterThan(collapsed * 3)
  await expect(fullText).toHaveText(long)

  await citations(page, 'S2').click()
  await expect.poll(async () => (await fullText.boundingBox())!.height).toBe(collapsed)
})

test('a double click opens the source in its document; its selection and marks stay', async ({ page }) => {
  await useViewport(page, 'narrow')
  await askBoth(page)
  const scrollBefore = await scrollY(page)

  await answer(page, 'A fire').getByRole('link', { name: '[S2]' }).first().dblclick()
  await expect(title(page)).toHaveText('Document')
  await expect(match(page)).toContainText(text('chronicle_3'))
  await expect(match(page).getByTestId('chunk-context-target-label')).toHaveText('S2')
  await expect(match(page)).toHaveAttribute('aria-label', 'Cited passage S2')
  await expect(documentPanel(page).getByTestId('chunk-context-header')).toContainText(chronicle.properties.title)
  await expect(selectedCitations(page)).toHaveCount(3)

  // Navigating the document and the panels keeps the selection.
  await documentPanel(page).locator('.chunk-context__chunk').first().scrollIntoViewIfNeeded()
  await documentPanel(page).getByRole('button', { name: 'Return to cited passage' }).click()
  await expect(match(page)).toBeInViewport()
  await sidebarPanelButton(page, 'Sources').click()
  await expect(sourceSummary(page, 'S2')).toHaveAttribute('aria-expanded', 'true')
  await sidebarPanelButton(page, 'Document').click()
  await expect(match(page)).toContainText(text('chronicle_3'))
  await expect(selectedCitations(page)).toHaveCount(3)

  // From the list: a double click on a source, or View document.
  await sidebarPanelButton(page, 'Sources').click()
  await sourceSummary(page, 'S3').dblclick()
  await expect(title(page)).toHaveText('Document')
  await expect(match(page)).toContainText(text('gazette_1'))
  await expect(match(page).getByTestId('chunk-context-target-label')).toHaveText('S3')
  await expect(documentPanel(page)).not.toContainText(chronicle.properties.title)
  await sidebarPanelButton(page, 'Sources').click()
  await sourceSummary(page, 'S1').click()
  // Another selection closes the previous source's document.
  await expect(sidebarPanelButton(page, 'Document')).toHaveCount(0)
  await sourceItem(page, 'S1').getByRole('button', { name: 'View source S1 in its document' }).click()
  await expect(match(page)).toContainText(text('chronicle_1'))
  await expect(match(page).getByTestId('chunk-context-target-label')).toHaveText('S1')

  expect(await scrollY(page)).toBe(scrollBefore)
})

test('resetting the chat closes the sources; the next conversation starts at S1', async ({ page }) => {
  await useViewport(page, 'narrow')
  await askBoth(page)
  await citations(page, 'S2').first().dblclick()
  await expect(match(page)).toContainText(text('chronicle_3'))

  await page.getByTitle('Reset chat').click()
  await expect(page.getByRole('button', { name: 'Toggle sidebar' })).toHaveCount(0)
  await expect(page.locator('.q-drawer--right')).toBeHidden()
  await expect(answer(page, 'A fire')).toHaveCount(0)

  await page.unroute('**/api/rag')
  await answerChat(page, [answers[1]])
  await askChat(page, 'What is in the gazette?')
  await expect(answer(page, 'The gazette has')).toContainText('a café [S1], the same fire [S2]')
  await expect(sourcesPanel(page).getByRole('listitem')).toHaveCount(2)
  await expect(selectedCitations(page)).toHaveCount(0)
})

test('a source that is no longer stored is reported, not replaced', async ({ page }) => {
  await useViewport(page, 'narrow')
  const missing = { ...chatSource('chronicle_2'), id: '5e3a0000-0000-4000-8000-0000000d1fff' }
  await answerChat(page, [{ rag_answer: 'An answer from a removed passage [doc 1].', sources: [missing] }])
  await openChat(page)
  await askChat(page, 'Question')

  await citations(page, 'S1').dblclick()
  await expect(documentPanel(page).getByRole('alert')).toContainText('no longer available')
  await expect(documentPanel(page).locator('.chunk-context__chunk')).toHaveCount(0)
  // The source's own text stays available.
  await sidebarPanelButton(page, 'Sources').click()
  await expect(sourceItem(page, 'S1')).toContainText(text('chronicle_2'))
})

test('a citation in an explanation selects the source beside the chat', async ({ page }) => {
  await useViewport(page, 'narrow')
  // The explanation cites the explained answer's own doc 1.
  await page.route('**/api/rag/explain', (route) => route.fulfill({ json: { explanation: 'It is stated in [doc 1].' } }))
  await askBoth(page)

  const answerText = answer(page, 'The gazette has').locator('.markdown-body')
  await answerText.selectText()
  await answerText.dispatchEvent('mouseup')
  await page.getByRole('button', { name: 'Explain' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('It is stated in [S3].')
  await dialog.getByRole('link', { name: '[S3]' }).click()

  await expect(dialog).toHaveCount(0)
  await expect(title(page)).toHaveText('Sources')
  await expect(sourceSummary(page, 'S3')).toHaveAttribute('aria-expanded', 'true')
  await expect(selectedCitations(page)).toHaveText(['[S3]'])
})

test('on a phone the sources are an overlay over the chat', async ({ page }) => {
  await useViewport(page, 'phone')
  await askBoth(page)
  // The sidebar does not cover the chat by itself.
  await expect(page.locator('.q-drawer--right')).toBeHidden()

  await answer(page, 'The gazette has').getByRole('link', { name: '[S3]' }).click()
  await expect(sourceSummary(page, 'S3')).toHaveAttribute('aria-expanded', 'true')
  await expect(sourceItem(page, 'S3')).toBeInViewport()
  // The list fits the phone without horizontal scrolling.
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)

  await sourceSummary(page, 'S3').dblclick()
  await expect(match(page)).toBeInViewport()
  await expect(match(page).getByTestId('chunk-context-target-label')).toHaveText('S3')

  // The overlay covers the header's toggle; its own button returns to the chat with the marks.
  await page.getByRole('button', { name: 'Close sidebar' }).click()
  await expect(page.locator('.q-drawer--right')).toBeHidden()
  await expect(answer(page, 'The gazette has')).toBeInViewport()
  await expect(selectedCitations(page)).toHaveText(['[S3]'])
})

test('a web search result is a source of its own, without a document to open', async ({ page }) => {
  // #370: the web fallback's results are distinct sources that are not in the corpus.
  const web = (n: number) => {
    const id = crypto.randomUUID()
    return {
      id,
      text: `Web snippet ${n} about Lhota.`,
      title: `Lhota web page ${n}`,
      start_page_id: id,
      from_page: 0,
      to_page: 0,
      document: id,
      order: 0,
      origin: 'web',
      document_object: { id, title: `Lhota web page ${n}`, url: `https://example.org/${n}` }
    }
  }
  await useViewport(page, 'narrow')
  await answerChat(page, [{
    rag_answer: 'The chronicle [doc 1], one page [doc 2] and another [doc 3].',
    sources: [chatSource('chronicle_1'), web(1), web(2)]
  }])
  await openChat(page)
  await askChat(page, 'What happened in Lhota?')

  await expect(answer(page, 'The chronicle')).toContainText('The chronicle [S1], one page [S2] and another [S3].')
  // A double click on the web citation selects the source; there is no document to show.
  await citations(page, 'S2').dblclick()
  await expect(title(page)).toHaveText('Sources')
  await expect(sourceSummary(page, 'S2')).toHaveAttribute('aria-expanded', 'true')
  await expect(sourceItem(page, 'S2')).toContainText('Web snippet 1 about Lhota.')
  await expect(sourceItem(page, 'S2')).toContainText('Web search result, not in the corpus')
  await expect(sourceItem(page, 'S2').getByRole('button', { name: /View source/ })).toHaveCount(0)
  await sourceSummary(page, 'S2').dblclick()
  await expect(documentPanel(page)).toHaveCount(0)
  await expect(selectedCitations(page)).toHaveText(['[S2]'])

  // The corpus source still opens.
  await sourceItem(page, 'S1').getByRole('button', { name: 'View source S1 in its document' }).click()
  await expect(match(page).getByTestId('chunk-context-target-label')).toHaveText('S1')
})
