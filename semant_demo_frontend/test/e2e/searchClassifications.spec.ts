import { expect, test } from '@playwright/test'

import { fixture } from './support'

// Stored chunk classifications (fixture corpus `chunk_classifications`) on Search results.

test('search results show their classifications with per-result expansion', async ({ page }) => {
  await page.goto('/#/search')
  await page.getByRole('textbox').first().fill('Lhota')
  await page.keyboard.press('Enter')

  const chronicle = page.locator('.q-card', { hasText: fixture.chunk('chronicle_1').text })
  const letter = page.locator('.q-card', { hasText: fixture.chunk('letters_1').text })
  const gazette = page.locator('.q-card', { hasText: fixture.chunk('gazette_1').text })
  await expect(chronicle).toContainText('Communicative Mode: Narration')
  await expect(chronicle).toContainText('Style: Formal')
  await expect(chronicle).not.toContainText('Subject Domain')
  await expect(letter).toContainText('Style: Informal')
  await expect(gazette.locator('.result-classifications')).toHaveCount(0)

  await chronicle.getByRole('button', { name: 'Show more (1)' }).click()
  await expect(chronicle).toContainText('Subject Domain: DDC 900 History Geography, News And Current Affairs')
  await expect(letter.getByRole('button')).toHaveCount(0) // two classifications: nothing to expand

  await chronicle.getByRole('button', { name: 'Show less' }).click()
  await expect(chronicle).not.toContainText('Subject Domain')
})
