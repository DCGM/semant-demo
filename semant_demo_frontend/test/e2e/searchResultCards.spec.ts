import { expect, test, type Page } from '@playwright/test'

import { fixture, logIn } from './support'

// Search result cards: selection checkbox left of the title, an understated selected state,
// and the complete passage text at desktop and phone widths.

async function search (page: Page, query: string) {
  await page.goto('/#/search')
  await page.getByRole('textbox').first().fill(query)
  await page.keyboard.press('Enter')
  await expect(page.locator('#result-1')).toBeVisible()
}

for (const { name, width, height } of [
  { name: 'desktop', width: 1280, height: 900 },
  { name: 'phone', width: 390, height: 844 }
]) {
  test(`result cards on ${name}: left checkbox, selection and complete text`, async ({ page }) => {
    await logIn(page, 'owner') // the selection actions are for signed-in users
    await page.setViewportSize({ width, height }) // after logging in, as in the navigation tests
    await search(page, 'Lhota')

    const chunk = fixture.chunk('chronicle_1')
    const card = page.locator('.search-result', { hasText: chunk.text })
    const checkbox = card.getByRole('checkbox', { name: /^Select result \d+: / })
    const title = card.locator('.search-result__title')

    // Left of the title, on the title's first line.
    const box = await checkbox.boundingBox()
    const titleBox = await title.boundingBox()
    const cardBox = await card.boundingBox()
    expect(box && titleBox && cardBox).toBeTruthy()
    expect(box!.x + box!.width).toBeLessThanOrEqual(titleBox!.x)
    expect(box!.x - cardBox!.x).toBeLessThan(32)
    expect(Math.abs(box!.y - titleBox!.y)).toBeLessThan(16)

    // No horizontal overflow of the card at this width.
    expect(await card.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true)

    // Complete passage: same text, nothing clipped, no Show more.
    const text = card.locator('.search-result__text')
    await expect(text).toHaveText(chunk.text)
    expect(await text.evaluate(el => el.scrollHeight <= el.clientHeight && getComputedStyle(el).overflow === 'visible')).toBe(true)
    await expect(card.getByRole('button', { name: /show more/i })).toHaveCount(0)
    await expect(card).toContainText(`Source: ${fixture.document('chronicle').properties.title}`)

    // Keyboard selection: focus ring and selected state are separate cues.
    const background = () => card.evaluate(el => getComputedStyle(el).backgroundColor)
    const unselected = await background()
    await checkbox.focus()
    await page.keyboard.press('Space')
    await expect(checkbox).toHaveAttribute('aria-checked', 'true')
    await expect(card).toHaveClass(/search-result--selected/)
    expect(await background()).not.toBe(unselected)
    await expect(checkbox).toBeFocused()
    await expect(page.getByText('1 item(s) selected')).toBeVisible()

    // Multi-select across cards; the toolbar's clear action resets both.
    const other = page.locator('.search-result').filter({ hasNotText: chunk.text }).first()
    await other.getByRole('checkbox').click()
    await expect(page.getByText('2 item(s) selected')).toBeVisible()
    await page.getByRole('button', { name: 'Add Chunks' }).scrollIntoViewIfNeeded()
    await expect(page.getByRole('button', { name: 'Add Chunks' })).toBeVisible()
    await page.locator('.q-card.bg-primary .q-btn').filter({ has: page.locator('i', { hasText: 'close' }) }).click()
    await expect(page.locator('.search-result--selected')).toHaveCount(0)
    await expect(checkbox).toHaveAttribute('aria-checked', 'false')
  })
}
