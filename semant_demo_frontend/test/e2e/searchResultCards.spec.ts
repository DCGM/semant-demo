import { expect, test, type Locator, type Page } from '@playwright/test'

import { fixture, logIn } from './support'

// Search result cards (#256): checkbox left of the title only, an understated selected
// state, passage previews in narrow result columns, the selection toolbar and Escape.

const chronicle = fixture.chunk('chronicle_1')
// The fixture passages are a line long; the browser gets a long one for chronicle_1.
const longText = [chronicle.text, ...Array.from({ length: 12 }, (_, i) =>
  `Odstavec ${i + 1}: kronikář pečlivě zapsal, kdo do obce přijel, kde se ubytoval a co se ten den v hostinci U Lípy projednávalo.`)].join('\n')

type SearchResponse = { results: { id: string, text: string }[] }

/** Lengthens chronicle_1 and, with `copies`, appends copies of the results (for pagination). */
async function patchSearch (page: Page, copies = 0) {
  await page.route('**/api/search', async (route) => {
    const response = await route.fetch()
    const body = await response.json() as SearchResponse
    for (const result of body.results) {
      if (result.text === chronicle.text) result.text = longText
    }
    const original = body.results
    for (let copy = 1; copy <= copies; copy++) {
      body.results = body.results.concat(original.map(r => ({ ...r, id: `${r.id}-copy-${copy}` })))
    }
    await route.fulfill({ response, json: body })
  })
}

async function search (page: Page, query = 'Lhota') {
  await page.goto('/#/search')
  await page.getByRole('textbox').first().fill(query)
  await page.keyboard.press('Enter')
  await expect(page.locator('#result-1')).toBeVisible()
  // On a phone the navigation starts open as an overlay; tap beside it to close it.
  const viewport = page.viewportSize()
  if (viewport && viewport.width < 600) {
    const backdrop = page.locator('.q-drawer__backdrop:not(.hidden)')
    await backdrop.first().click({ position: { x: viewport.width - 20, y: viewport.height / 2 } })
    await expect(backdrop).toHaveCount(0)
  }
}

async function box (locator: Locator) {
  const b = await locator.boundingBox()
  if (!b) throw new Error('element has no box')
  return b
}

const card = (page: Page, text = chronicle.text) => page.locator('.search-result', { hasText: text })
const clipped = (text: Locator) => text.evaluate(el => el.scrollHeight > el.clientHeight + 1)
const toolbar = (page: Page) => page.locator('.selection-toolbar')

for (const { name, width, height, constrained } of [
  { name: 'wide desktop', width: 1920, height: 1000, constrained: false },
  { name: 'narrow desktop with both sidebars', width: 1280, height: 900, constrained: true },
  { name: 'phone', width: 390, height: 844, constrained: true }
]) {
  test(`result cards on ${name}: alignment, passage and keyboard selection`, async ({ page }) => {
    await page.setViewportSize({ width, height })
    await patchSearch(page)
    await search(page)

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
    await expect(text).toHaveText(longText)
    await expect(result).toContainText(`Source: ${fixture.document('chronicle').properties.title}`)
    const showFull = result.getByRole('button', { name: 'Show full text' })
    if (!constrained) {
      expect(await clipped(text)).toBe(false)
      await expect(showFull).toHaveCount(0)
    } else {
      expect(await clipped(text)).toBe(true)
      const lines = await text.evaluate(el => el.clientHeight / parseFloat(getComputedStyle(el).lineHeight))
      expect(lines).toBeGreaterThanOrEqual(5)
      expect(lines).toBeLessThanOrEqual(6.5)
      await expect(card(page, fixture.chunk('chronicle_3').text).getByRole('button', { name: 'Show full text' })).toHaveCount(0) // fits

      await showFull.click()
      expect(await clipped(text)).toBe(false)
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
    expect(await background()).not.toBe(unselected)
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
  await logIn(page, 'annotator') // only a shared collection
  await search(page)
  await card(page).getByRole('checkbox').click()
  await expect(toolbar(page)).toContainText('1 item(s) selected')
  await expect(toolbar(page).getByRole('button', { name: 'Clear selection' })).toBeVisible()
  await expect(toolbar(page).getByRole('button', { name: 'Add Chunks' })).toHaveCount(0)
  await expect(toolbar(page).getByRole('button', { name: 'Add Documents' })).toHaveCount(0)
  await expect(toolbar(page).getByLabel('Select Collection')).toHaveCount(0)
})

test('the collection owner gets the collection actions', async ({ page }) => {
  await logIn(page, 'owner')
  await search(page)
  await card(page).getByRole('checkbox').click()
  await expect(toolbar(page).getByLabel('Select Collection')).toBeVisible()
  await expect(toolbar(page).getByRole('button', { name: 'Add Chunks' })).toBeVisible()
  await expect(toolbar(page).getByRole('button', { name: 'Add Documents' })).toBeVisible()
  await toolbar(page).getByRole('button', { name: 'Clear selection' }).click()
  await expect(toolbar(page)).toBeHidden()
})

test('Escape clears the selection on all pages, but not inside a field or menu', async ({ page }) => {
  await logIn(page, 'owner')
  await patchSearch(page, 2) // more than one page of results
  await search(page)
  const selected = page.locator('.search-result--selected')

  await page.locator('#result-1').getByRole('checkbox').click()
  const pageButton = (n: number) => page.locator('.q-pagination button').filter({ hasText: new RegExp(`^${n}$`) })
  await pageButton(2).click()
  await page.locator('#result-11').getByRole('checkbox').click()
  await expect(toolbar(page)).toContainText('2 item(s) selected')

  // In the search field Escape belongs to the field.
  await page.getByRole('textbox').first().focus()
  await page.keyboard.press('Escape')
  await expect(toolbar(page)).toContainText('2 item(s) selected')

  // An open menu closes first; the selection stays.
  await toolbar(page).getByLabel('Select Collection').click()
  await expect(page.locator('.q-menu')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.locator('.q-menu')).toHaveCount(0)
  await expect(toolbar(page)).toContainText('2 item(s) selected')

  // Otherwise it clears all pages.
  await page.locator('#result-11 .search-result__title').click()
  await page.keyboard.press('Escape')
  await expect(toolbar(page)).toBeHidden()
  await expect(selected).toHaveCount(0)
  await pageButton(1).click()
  await expect(selected).toHaveCount(0)
})
