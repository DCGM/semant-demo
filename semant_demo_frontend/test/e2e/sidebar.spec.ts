import { expect, test } from '@playwright/test'

// App-level right sidebar with the search-summary panel. The e2e profile's fake Ollama
// answers "Fake summary of N passage(s); last [docN]." for the passages it was sent, so the
// cited result shows which results were summarized.

test('search summary in the sidebar works on the selected results only', async ({ page }) => {
  await page.goto('/#/search')
  const sidebarToggle = page.getByRole('button', { name: 'Toggle sidebar' })
  await expect(sidebarToggle).toHaveCount(0) // no panel before there are results

  await page.getByRole('textbox').first().fill('Lhota')
  await page.keyboard.press('Enter')
  await expect(page.locator('#result-2')).toBeVisible()
  await expect(sidebarToggle).toBeVisible()
  await expect(page.getByRole('listitem', { name: 'Summary' })).toBeVisible()

  // Select the second result only: the summary scope switches to "Selected".
  await page.locator('#result-2 .q-checkbox').click()
  await page.getByRole('button', { name: 'Summarize Results' }).click()

  const summary = page.getByTestId('search-summary')
  await expect(summary).toContainText('Fake summary of 1 passage(s); last [2].')
  await summary.getByRole('link', { name: '[2]' }).click()
  await expect(page.locator('#result-2')).toHaveClass(/citation-target-highlight/)

  // A new search is a new context: the old summary does not stay next to its results.
  await page.getByRole('textbox').first().fill('Brno')
  await page.keyboard.press('Enter')
  await expect(summary).toHaveCount(0)
})

test('the sidebar goes away with the page that registered its panel', async ({ page }) => {
  await page.goto('/#/search')
  await page.getByRole('textbox').first().fill('Lhota')
  await page.keyboard.press('Enter')
  await expect(page.getByRole('button', { name: 'Toggle sidebar' })).toBeVisible()

  await page.locator('.q-drawer').getByText('Collections', { exact: true }).click()

  await expect(page.getByRole('button', { name: 'Toggle sidebar' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Summarize Results' })).toHaveCount(0)
})
