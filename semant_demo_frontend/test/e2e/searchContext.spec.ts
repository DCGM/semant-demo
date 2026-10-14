import { expect, test, type Page } from '@playwright/test'

import { appendResultCopies, editSearchResults, fixture, goToResultsPage, search, useViewport } from './support'

// A search result in its document context (#244): the "Document" panel of the right
// sidebar reads a bounded passage of the public corpus around the hit and highlights it.

const chronicle = [fixture.chunk('chronicle_1'), fixture.chunk('chronicle_2'), fixture.chunk('chronicle_3')]
const chronicleTitle = fixture.document('chronicle').properties.title

const card = (page: Page, text: string) => page.locator('.search-result', { hasText: text }).first()
const panel = (page: Page) => page.getByTestId('chunk-context')
const match = (page: Page) => panel(page).locator('[aria-current="true"]')

test('double-clicking a result shows it highlighted in its document', async ({ page }) => {
  await useViewport(page, 'narrow')
  await search(page, 'Lhota')
  // Summary stays the default panel; Document appears once a result is opened.
  await expect(page.getByTestId('right-sidebar-title')).toHaveText('Summary')
  await expect(page.getByRole('listitem', { name: 'Document' })).toHaveCount(0)
  const result = card(page, chronicle[1].text)

  await result.locator('.search-result__text').dblclick()

  await expect(page.getByTestId('right-sidebar-title')).toHaveText('Document')
  await expect(match(page)).toHaveText(new RegExp(chronicle[1].text))
  const header = panel(page).getByTestId('chunk-context-header')
  await expect(header).toContainText(chronicleTitle)
  await expect(header).toContainText(`${fixture.document('chronicle').properties.yearIssued}`)
  await expect(header.getByRole('button', { name: 'Focus on result' })).toBeVisible()
  // The neighbours are context, not matches.
  await expect(panel(page).locator('.chunk-context__chunk')).toHaveText(chronicle.map(c => new RegExp(c.text)))
  await expect(panel(page)).toContainText('Start of document')
  await expect(panel(page)).toContainText('End of document')
  // Double-click did not select the result.
  await expect(result.getByRole('checkbox')).toHaveAttribute('aria-checked', 'false')
  await expect(page.locator('.selection-toolbar')).toBeHidden()

  // Another result replaces the passage; nothing of the previous document stays.
  const letters = fixture.chunk('letters_1')
  await card(page, letters.text).getByRole('button', { name: /in its document$/ }).click()
  await expect(match(page)).toHaveText(new RegExp(letters.text))
  await expect(panel(page)).not.toContainText(chronicleTitle)

  // The Summary panel still works next to it.
  await page.getByRole('listitem', { name: 'Summary' }).click()
  await page.getByRole('button', { name: 'Summarize Results' }).click()
  await expect(page.getByTestId('search-summary')).toContainText('Fake summary of')

  // A new search closes the old result's context.
  await page.getByRole('listitem', { name: 'Document' }).click()
  await page.getByRole('textbox').first().fill('Brno')
  await page.keyboard.press('Enter')
  await expect(page.locator('#result-1')).toBeVisible()
  await expect(panel(page)).toHaveCount(0)
  await expect(page.getByRole('listitem', { name: 'Document' })).toHaveCount(0)
  await expect(page.getByTestId('right-sidebar-title')).toHaveText('Summary')
})

test('Focus on result restores its page; unknown chunks fail safely', async ({ page }) => {
  await useViewport(page, 'narrow')
  await editSearchResults(page, (body) => appendResultCopies(body, 1)) // copies are unknown chunks
  await search(page, 'Lhota')
  const result = page.locator('#result-1')

  await result.getByRole('button', { name: /in its document$/ }).click()
  await expect(match(page)).toBeVisible()

  // Browse elsewhere in the results, then come back.
  await goToResultsPage(page, 2)
  await expect(page.locator('#result-11')).toBeVisible()
  await expect(result).toHaveCount(0)
  await panel(page).getByRole('button', { name: 'Focus on result' }).click()
  await expect(result).toBeVisible()
  await expect(result).toHaveClass(/citation-target-highlight/)
  await expect(result).toBeInViewport()

  // A result whose chunk does not exist (deleted meanwhile) shows an error, not other text.
  await goToResultsPage(page, 2)
  await page.locator('#result-11').getByRole('button', { name: /in its document$/ }).click()
  await expect(panel(page).getByRole('alert')).toContainText('no longer available')
  await expect(panel(page).locator('.chunk-context__chunk')).toHaveCount(0)
})

test('on a phone the context is an overlay and Focus on result closes it', async ({ page }) => {
  await useViewport(page, 'phone')
  await search(page, 'Lhota')

  await page.locator('#result-1').getByRole('button', { name: /in its document$/ }).click()
  await expect(match(page)).toBeVisible()
  await expect(match(page)).toBeInViewport()

  await panel(page).getByRole('button', { name: 'Focus on result' }).click()
  await expect(page.locator('.q-drawer--right')).toBeHidden()
  await expect(page.locator('#result-1')).toBeInViewport()
})
