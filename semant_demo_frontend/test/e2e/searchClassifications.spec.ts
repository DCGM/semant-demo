import { expect, test } from '@playwright/test'

import { fixture } from './support'

// Stored chunk classifications (fixture corpus `chunk_classifications`) on Search results:
// one line of value badges, expandable when they need more.

test('search results show classification badges on one expandable line', async ({ page }) => {
  // Narrow result column (sidebar open): chronicle_1's five badges need two lines, letters_1's two fit.
  await page.setViewportSize({ width: 1100, height: 900 })
  await page.goto('/#/search')
  await page.getByRole('textbox').first().fill('Lhota')
  await page.keyboard.press('Enter')

  const chronicle = page.locator('.q-card', { hasText: fixture.chunk('chronicle_1').text })
  const letter = page.locator('.q-card', { hasText: fixture.chunk('letters_1').text })
  const gazette = page.locator('.q-card', { hasText: fixture.chunk('gazette_1').text })
  const badges = chronicle.locator('.classification-badge')

  await expect(badges).toHaveCount(5)
  await expect(badges.first()).toHaveText('Communicative Mode: Narration') // category for screen readers
  await expect(badges.first()).toHaveClass(/bg-orange-1/) // color of its search filter's position
  await expect(letter.locator('.classification-badge').last()).toHaveClass(/bg-teal-4/) // style
  await expect(letter.locator('.classification-badge')).toHaveText(['Communicative Mode: Interaction', 'Style: Informal'])
  await expect(letter.getByRole('button')).toHaveCount(0) // fits on one line
  await expect(gazette.locator('.result-classifications')).toHaveCount(0)

  const line = chronicle.locator('.classification-line')
  const clipped = () => line.evaluate((el) => el.scrollHeight > el.clientHeight)
  await expect.poll(clipped).toBe(true) // badges below the first line are hidden
  await chronicle.getByRole('button', { name: /^\+\d+ more$/ }).click()
  await expect.poll(clipped).toBe(false)
  await expect(badges.last()).toHaveText('Subject Domain: News And Current Affairs')

  await chronicle.getByRole('button', { name: 'Show less' }).click()
  await expect(chronicle.getByRole('button', { name: /^\+\d+ more$/ })).toBeVisible()
})
