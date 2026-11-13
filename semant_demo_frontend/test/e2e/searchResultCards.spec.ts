import { expect, test, type Locator, type Page } from '@playwright/test'

import { LONG_PASSAGE_TERM, LONG_PASSAGE_TEXT, LONG_PASSAGE_TOKEN } from '../fixtures/longPassage'
import { appendResultCopies, editSearchResults, ensureLoggedIn, fixture, insertLongPassage, LONG_PASSAGE_CHUNK, search, useLongPassage, useViewport } from './support'

// Search result cards (#256): checkbox left of the title only, an understated selected
// state, passage previews in narrow result columns, the selection toolbar and Escape.
// The fixture passages are a line long; the shared long multilingual passage (#274) stands
// in for chronicle_1's text.

const chronicle = fixture.chunk(LONG_PASSAGE_CHUNK)

async function box (locator: Locator) {
  const b = await locator.boundingBox()
  if (!b) throw new Error('element has no box')
  return b
}

const card = (page: Page, text = LONG_PASSAGE_TERM) => page.locator('.search-result', { hasText: text })
const renderedText = (text: Locator) => text.evaluate(el => (el as HTMLElement).innerText)
const visible = (text: Locator, index: number) => text.evaluate((el, i) => {
  const range = document.createRange()
  range.setStart(el.firstChild as Text, i)
  range.setEnd(el.firstChild as Text, i + 1)
  const [char, box] = [range.getBoundingClientRect(), el.getBoundingClientRect()]
  return char.top >= box.top - 1 && char.bottom <= box.bottom + 1 && char.right <= box.right + 1
}, index)
const clipped = (text: Locator) => text.evaluate(el => el.scrollHeight > el.clientHeight + 1)
const toolbar = (page: Page) => page.locator('.selection-toolbar')

for (const { name, viewport, constrained } of [
  { name: 'wide desktop', viewport: 'wide', constrained: false },
  { name: 'narrow desktop with both sidebars', viewport: 'narrow', constrained: true },
  { name: 'phone', viewport: 'phone', constrained: true }
] as const) {
  test(`result cards on ${name}: alignment, passage and keyboard selection`, async ({ page }) => {
    await useViewport(page, viewport)
    await useLongPassage(page)
    await search(page, 'Lhota')

    if (name.includes('sidebars')) {
      await expect(page.locator('.q-drawer--left')).toBeVisible()
      await expect(page.locator('.q-drawer--left')).not.toHaveClass(/q-drawer--mini/)
      await expect(page.locator('.q-drawer--right')).toBeVisible()
    }

    const result = card(page)
    const checkbox = result.getByRole('checkbox', { name: /^Select result \d+: / })
    const title = result.locator('.search-result__title')
    const text = result.locator('.search-result__text')

    // Checkbox left of the title, on its first line; only the title is indented.
    const [cardBox, checkBox, titleBox, metaBox, sourceBox, textBox] = await Promise.all(
      [result, checkbox, title, result.locator('.search-result__meta'), result.locator('.search-result__source'), text].map(box))
    expect(checkBox.x + checkBox.width).toBeLessThanOrEqual(titleBox.x)
    expect(checkBox.x - cardBox.x).toBeLessThan(32)
    expect(Math.abs(checkBox.y - titleBox.y)).toBeLessThan(16)
    expect(Math.abs(metaBox.x - textBox.x)).toBeLessThanOrEqual(1)
    expect(Math.abs(sourceBox.x - textBox.x)).toBeLessThanOrEqual(1)
    expect(titleBox.x - metaBox.x).toBeGreaterThan(16)
    expect(await result.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true)

    // The passage: complete when wide; a ~6-line preview with Show full text when narrow.
    expect(await renderedText(text)).toBe(LONG_PASSAGE_TEXT)

    const { title: source, author, yearIssued } = fixture.document('chronicle').properties
    await expect(result).toContainText(`Source: ${source}`)
    await expect(result.locator('.search-result__meta')).toContainText(author?.join(', ') ?? 'missing author')
    await expect(result.locator('.search-result__meta')).toContainText(String(yearIssued))
    const showFull = result.getByRole('button', { name: 'Show full text' })
    if (!constrained) {
      expect(await clipped(text)).toBe(false)
      await expect(showFull).toHaveCount(0)
      expect(await visible(text, 0)).toBe(true)
      expect(await visible(text, LONG_PASSAGE_TEXT.length - 1)).toBe(true)
    } else {
      expect(await clipped(text)).toBe(true)
      expect(await visible(text, 0)).toBe(true)
      expect(await visible(text, LONG_PASSAGE_TEXT.length - 1)).toBe(false)
      const lines = await text.evaluate(el => el.clientHeight / parseFloat(getComputedStyle(el).lineHeight))
      expect(lines).toBeGreaterThanOrEqual(5)
      expect(lines).toBeLessThanOrEqual(6.5)
      await expect(card(page, fixture.chunk('chronicle_3').text).getByRole('button', { name: 'Show full text' })).toHaveCount(0) // fits

      await showFull.click()
      expect(await clipped(text)).toBe(false)
      expect(await visible(text, LONG_PASSAGE_TEXT.length - 1)).toBe(true)
      expect(await visible(text, LONG_PASSAGE_TEXT.indexOf(LONG_PASSAGE_TOKEN) + LONG_PASSAGE_TOKEN.length - 1)).toBe(true)
      expect(await renderedText(text)).toBe(LONG_PASSAGE_TEXT)
      const showLess = result.getByRole('button', { name: 'Show less' })
      await expect(showLess).toHaveAttribute('aria-expanded', 'true')
      await showLess.click()
      expect(await clipped(text)).toBe(true)
    }

    // Keyboard selection: focus ring and selected state are separate cues.
    const background = () => result.evaluate(el => getComputedStyle(el).backgroundColor)
    const unselected = await background()
    await checkbox.focus()
    await page.keyboard.press('Space')
    await expect(checkbox).toHaveAttribute('aria-checked', 'true')
    await expect(result).toHaveClass(/search-result--selected/)
    // Polled: the card animates its background (0.15 s), so one read can still see the old one.
    await expect.poll(background).not.toBe(unselected)
    await expect(checkbox).toBeFocused()

    // Signed out: count and Clear selection, no collection actions.
    await expect(toolbar(page)).toContainText('1 item(s) selected')
    await expect(toolbar(page).getByRole('button', { name: 'Clear selection' })).toBeVisible()
    await expect(toolbar(page).getByRole('button', { name: 'Add Chunks' })).toHaveCount(0)
    expect(await toolbar(page).evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true)

    await page.keyboard.press('Escape') // from the focused checkbox
    await expect(page.locator('.search-result--selected')).toHaveCount(0)
    await expect(toolbar(page)).toBeHidden()
  })
}

test('a signed-in user without membership rights gets no collection actions', async ({ page }) => {
  await ensureLoggedIn(page, 'annotator') // only a shared collection
  await search(page, 'Lhota')
  await card(page, chronicle.text).getByRole('checkbox').click()
  await expect(toolbar(page)).toContainText('1 item(s) selected')
  await expect(toolbar(page).getByRole('button', { name: 'Clear selection' })).toBeVisible()
  await expect(toolbar(page).getByRole('button', { name: 'Add Chunks' })).toHaveCount(0)
  await expect(toolbar(page).getByRole('button', { name: 'Add Documents' })).toHaveCount(0)
  await expect(toolbar(page).getByLabel('Select Collection')).toHaveCount(0)
})

test('the collection owner gets the collection actions', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await search(page, 'Lhota')
  await card(page, chronicle.text).getByRole('checkbox').click()
  await expect(toolbar(page).getByLabel('Select Collection')).toBeVisible()
  await expect(toolbar(page).getByRole('button', { name: 'Add Chunks' })).toBeVisible()
  await expect(toolbar(page).getByRole('button', { name: 'Add Documents' })).toBeVisible()
  await toolbar(page).getByRole('button', { name: 'Clear selection' }).click()
  await expect(toolbar(page)).toBeHidden()
})

test('Escape clears the whole selection, but not inside a field or menu', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await editSearchResults(page, (body) => { insertLongPassage(body); appendResultCopies(body, 2) })
  await search(page, 'Lhota')
  const selected = page.locator('.search-result--selected')

  await page.locator('#result-1').getByRole('checkbox').click()
  await page.locator('#result-11').getByRole('checkbox').click()
  await expect(toolbar(page)).toContainText('2 item(s) selected')

  // In the search field Escape belongs to the field.
  await page.getByRole('combobox', { name: 'Search query' }).focus()
  await page.keyboard.press('Escape')
  await expect(toolbar(page)).toContainText('2 item(s) selected')

  // An open menu closes first; the selection stays.
  await toolbar(page).getByLabel('Select Collection').click()
  await expect(page.locator('.q-menu')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.locator('.q-menu')).toHaveCount(0)
  await expect(toolbar(page)).toContainText('2 item(s) selected')

  // Otherwise it clears the whole selection, also of results out of view.
  await page.locator('#result-11 .search-result__title').click()
  await page.keyboard.press('Escape')
  await expect(toolbar(page)).toBeHidden()
  await expect(selected).toHaveCount(0)
})
