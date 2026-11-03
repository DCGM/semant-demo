import { expect, test, type Locator, type Page } from '@playwright/test'

import { closePhoneNavigation, fixture, useViewport } from './support'

// The scan viewer (#543) on its preview page, with the synthetic page fixtures of the
// browser-test profile (semant_demo_backend/tests/page_fixtures.py): line overlays stay on
// the scan's lines under zoom, pan, fit, resize and page changes; clicks report source line
// ids; smart focus moves the page only when a line is not visible enough; layouts load for
// the current page only, and a page left early never shows its lines.

const chronicle = fixture.document('chronicle')
const gazette = fixture.document('gazette')
const letters = fixture.document('letters')
const PAGE_1 = '5e3a0000-0000-4000-8000-0000000d1f01'
const PAGE_2 = '5e3a0000-0000-4000-8000-0000000d1f02'

const viewport = (page: Page) => page.getByTestId('scan-viewport')
const stage = (page: Page) => page.getByTestId('scan-stage')
const image = (page: Page) => page.locator('img.scan-view__image')
const line = (page: Page, id: string) => page.locator(`polygon.scan-line[data-line-id="${id}"]`)
const position = (page: Page) => page.getByTestId('page-position')

async function openScan (page: Page, documentId: string, pageId?: string) {
  await page.goto(`/#/preview/scan/${documentId}${pageId ? `?page=${pageId}` : ''}`)
  await closePhoneNavigation(page)
  await expect(page.getByTestId('document-image-pane')).toBeVisible()
}

/** Waits until the scan and its overlay are shown and the stage has stopped moving. */
async function settled (page: Page) {
  await expect(image(page)).toBeVisible()
  await expect.poll(() => image(page).evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true)
  await expect(page.getByTestId('scan-overlay')).toBeAttached()
  let last = ''
  await expect.poll(async () => {
    const now = await stage(page).evaluate(el => getComputedStyle(el).transform)
    const same = now === last
    last = now
    return same
  }).toBe(true)
}

/**
 * Where a layout line should be on screen: its baseline from the layout file, mapped through
 * the image's on-screen box. Independent of the overlay, so a misplaced overlay fails.
 */
async function expectedBox (page: Page, pageId: string, lineId: string) {
  const layout = await (await page.request.get(`/api/documents/${chronicle.id}/pages/${pageId}/layout`)).json()
  const l = layout.regions.flatMap((r: { lines: unknown[] }) => r.lines).find((x: { id: string }) => x.id === lineId)
  const box = (await image(page).boundingBox())!
  const k = box.width / layout.image.width
  const xs = l.baseline.map((p: number[]) => p[0])
  const ys = l.baseline.map((p: number[]) => p[1])
  return {
    left: box.x + Math.min(...xs) * k,
    right: box.x + Math.max(...xs) * k,
    top: box.y + (Math.min(...ys) - l.heights[0]) * k,
    bottom: box.y + (Math.max(...ys) + l.heights[1]) * k,
    scale: k
  }
}

/** The overlay polygon of the line covers the line's place on the scan (within 1.5 px). */
async function expectAligned (page: Page, pageId: string, lineId: string) {
  const expected = await expectedBox(page, pageId, lineId)
  const actual = (await line(page, lineId).boundingBox())!
  // The band's corners follow the baseline's normal, so allow for a skewed line's slant.
  const slack = 1.5 + 30 * expected.scale
  expect(Math.abs(actual.x - expected.left)).toBeLessThan(slack)
  expect(Math.abs(actual.x + actual.width - expected.right)).toBeLessThan(slack)
  expect(Math.abs(actual.y - expected.top)).toBeLessThan(slack)
  expect(Math.abs(actual.y + actual.height - expected.bottom)).toBeLessThan(slack)
}

async function centerOf (locator: Locator) {
  const b = (await locator.boundingBox())!
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 }
}

const transformOf = (page: Page) => stage(page).evaluate(el => el.style.transform)

test('line overlays stay on the scan lines through zoom, pan, fit, resize and page changes', async ({ page }) => {
  await useViewport(page, 'narrow')
  await openScan(page, chronicle.id, PAGE_1)
  await settled(page)
  await expectAligned(page, PAGE_1, 'r002-l001')
  await expectAligned(page, PAGE_1, 'r003-l002')

  await viewport(page).focus()
  await page.keyboard.press('+')
  await page.keyboard.press('+')
  await settled(page)
  await expectAligned(page, PAGE_1, 'r002-l001')

  // Drag the page.
  const c = await centerOf(viewport(page))
  await page.mouse.move(c.x, c.y)
  await page.mouse.down()
  await page.mouse.move(c.x - 120, c.y - 80, { steps: 5 })
  await page.mouse.up()
  await expectAligned(page, PAGE_1, 'r002-l001')

  // Wheel zoom about the pointer.
  await page.mouse.move(c.x, c.y)
  await page.mouse.wheel(0, -200)
  await settled(page)
  await expectAligned(page, PAGE_1, 'r003-l001')

  await page.setViewportSize({ width: 1000, height: 700 })
  await settled(page)
  await expectAligned(page, PAGE_1, 'r003-l001')

  await page.keyboard.press('0')
  await settled(page)
  await expectAligned(page, PAGE_1, 'r002-l003')
  const fitted = (await image(page).boundingBox())!
  const view = (await viewport(page).boundingBox())!
  // Fitted: the whole page inside the viewer.
  expect(fitted.y).toBeGreaterThanOrEqual(view.y)
  expect(fitted.y + fitted.height).toBeLessThanOrEqual(view.y + view.height + 0.5)

  await page.keyboard.press('PageDown')
  await expect(page).toHaveURL(new RegExp(`page=${PAGE_2}`))
  await settled(page)
  await expectAligned(page, PAGE_2, 'r002-l001') // the curved baseline
})

test('a clicked line reports its source ids and the approximate word start', async ({ page }) => {
  await useViewport(page, 'narrow')
  await openScan(page, chronicle.id, PAGE_1)
  await settled(page)
  const target = line(page, 'r002-l002')
  const box = (await target.boundingBox())!
  // A point on the right half of the line: past its first word.
  await page.mouse.click(box.x + box.width * 0.75, box.y + box.height * 0.6)
  await expect(page.getByTestId('scan-preview-event')).toHaveText(new RegExp(`^Selected line r002-l002 on page ${PAGE_1} at offset [1-9]\\d*$`))
  await expect(target).toHaveClass(/scan-line--active/)
  // A drag is not a click.
  const c = await centerOf(line(page, 'r002-l001'))
  await page.mouse.move(c.x, c.y)
  await page.mouse.down()
  await page.mouse.move(c.x + 60, c.y + 40, { steps: 4 })
  await page.mouse.up()
  await expect(target).toHaveClass(/scan-line--active/)
})

test('a two-finger pinch keeps the scan under the fingers while they also move', async ({ page }) => {
  await useViewport(page, 'narrow')
  await openScan(page, chronicle.id, PAGE_1)
  await settled(page)
  // Real touch input (Chromium turns it into pointer events), not synthetic events.
  const cdp = await page.context().newCDPSession(page)
  const touch = (type: 'touchStart' | 'touchMove' | 'touchEnd', points: Array<[number, number]>) => cdp.send('Input.dispatchTouchEvent', {
    type, touchPoints: points.map(([x, y], id) => ({ x, y, id }))
  })
  const target = await centerOf(line(page, 'r002-l002'))
  const before = (await image(page).boundingBox())!
  // The scan point under the starting midpoint, as a fraction of the image.
  const u = (target.x - before.x) / before.width
  const v = (target.y - before.y) / before.height

  await touch('touchStart', [[target.x - 30, target.y], [target.x + 30, target.y]])
  // Spread to twice the distance while the midpoint moves by (+40, +50).
  for (let i = 1; i <= 5; i++) {
    const spread = 30 + 6 * i
    const mx = target.x + 8 * i
    const my = target.y + 10 * i
    await touch('touchMove', [[mx - spread, my], [mx + spread, my]])
  }
  await touch('touchEnd', [])
  await settled(page)

  const after = (await image(page).boundingBox())!
  expect(after.width / before.width).toBeCloseTo(2, 1)
  // The same scan point is now under the fingers' final midpoint.
  expect(Math.abs(after.x + u * after.width - (target.x + 40))).toBeLessThan(2)
  expect(Math.abs(after.y + v * after.height - (target.y + 50))).toBeLessThan(2)
  await expectAligned(page, PAGE_1, 'r002-l002')
})

test('keyboard line steps and focus requests move the page only when the line is not visible enough', async ({ page }) => {
  await useViewport(page, 'narrow')
  await openScan(page, chronicle.id, PAGE_1)
  await settled(page)
  await viewport(page).focus()
  const fittedTransform = await transformOf(page)

  // Fitted, the lines are readable at this size: stepping through them does not move the page.
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('ArrowDown')
  await expect(line(page, 'r002-l001')).toHaveClass(/scan-line--active/)
  await expect(page.getByTestId('scan-preview-event')).toHaveText(`Focused line r002-l001 on page ${PAGE_1}`)
  await expect(page.getByTestId('line-announcement')).toContainText('Line 2 of')
  expect(await transformOf(page)).toBe(fittedTransform)

  // Zoomed in about the page's middle, the title line is out of view; a focus request pans to it.
  for (let i = 0; i < 6; i++) await page.keyboard.press('+')
  await settled(page)
  const zoomed = await transformOf(page)
  const view = (await viewport(page).boundingBox())!
  const before = (await line(page, 'r001-l001').boundingBox())!
  expect(before.y + before.height > view.y + view.height || before.y < view.y).toBe(true)
  expect(await page.evaluate(() => (window as unknown as { __scanPreview: { focus: (r: object) => Promise<boolean> } })
    .__scanPreview.focus({ pageId: '5e3a0000-0000-4000-8000-0000000d1f01', lineIds: ['r001-l001'] }))).toBe(true)
  await settled(page)
  const after = (await line(page, 'r001-l001').boundingBox())!
  expect(after.y).toBeGreaterThanOrEqual(view.y)
  expect(after.y + after.height).toBeLessThanOrEqual(view.y + view.height)
  // Panned, not zoomed: the scale part of the transform is unchanged.
  const scaleOf = (t: string) => t.match(/scale\(([^)]+)\)/)![1]
  expect(scaleOf(await transformOf(page))).toBe(scaleOf(zoomed))

  // A second request for the visible line changes nothing.
  const panned = await transformOf(page)
  await page.evaluate(() => (window as unknown as { __scanPreview: { focus: (r: object) => Promise<boolean> } })
    .__scanPreview.focus({ pageId: '5e3a0000-0000-4000-8000-0000000d1f01', lineIds: ['r001-l001'] }))
  await settled(page)
  expect(await transformOf(page)).toBe(panned)
})

test('pages and thumbnails load lazily, and a page left early never shows its lines', async ({ page }) => {
  await useViewport(page, 'wide')
  const layouts: string[] = []
  page.on('request', r => { if (r.url().endsWith('/layout')) layouts.push(r.url()) })
  await openScan(page, gazette.id)
  await expect(position(page)).toHaveText('1 / 120')
  // Only the thumbnails near the visible part of the strip are in the page.
  const thumbs = page.getByTestId('page-thumbnail')
  await expect(thumbs.first()).toBeVisible()
  expect(await thumbs.count()).toBeLessThan(60)
  await expect(page.getByRole('button', { name: 'Page [1], front cover' })).toHaveAttribute('aria-current', 'page')

  // Jump by printed label: page "100" is the 101st page.
  const jump = page.getByLabel('Go to page (printed label or position)')
  await jump.fill('100')
  await jump.press('Enter')
  await expect(position(page)).toHaveText('101 / 120')
  await expect(page.getByRole('button', { name: 'Page 100' })).toHaveAttribute('aria-current', 'page')
  await settled(page)
  // The cover has an empty layout; then only page 100's layout was read.
  expect(layouts.length).toBe(2)
  await jump.fill('999')
  await jump.press('Enter')
  await expect(page.getByText('No page "999"')).toBeVisible()

  // A slow layout of page "101"; leave it for "102" before it arrives.
  const manifest = await (await page.request.get(`/api/documents/${gazette.id}/pages`)).json()
  const [slow, shown] = [manifest.pages[101].page_id, manifest.pages[102].page_id]
  let release: () => void = () => undefined
  const held = new Promise<void>(resolve => { release = resolve })
  let delivered: () => void = () => undefined
  const answered = new Promise<void>(resolve => { delivered = resolve })
  await page.route(`**/pages/${slow}/layout`, async route => {
    await held
    await route.continue().catch(() => undefined)
    delivered()
  })
  await page.getByRole('button', { name: 'Next page' }).click()
  await expect(position(page)).toHaveText('102 / 120')
  await page.getByRole('button', { name: 'Next page' }).click()
  await expect(position(page)).toHaveText('103 / 120')
  await settled(page)
  release()
  await answered
  await expect(page.getByTestId('scan-overlay')).toHaveAttribute('data-layout-page-id', shown)
  await expect(page.locator('polygon.scan-line')).toHaveCount(5)
  await expect(page.getByRole('button', { name: 'Page 102' })).toHaveAttribute('aria-current', 'page')
})

test('covers, skipped numbers, missing layouts and scans, and text-only documents', async ({ page }) => {
  await useViewport(page, 'narrow')
  await openScan(page, chronicle.id)
  await expect(page.getByRole('button', { name: 'Page [1], front cover' })).toHaveAttribute('aria-current', 'page')
  await settled(page)
  await expect(page.locator('polygon.scan-line')).toHaveCount(0)

  // Labels skip from 3 to 6: the strip shows them as printed.
  await expect(page.getByTestId('page-thumbnail').locator('.page-strip__label')).toHaveText(['[1]', '1', '2', '3', '6', '7', '[8]'])
  await page.getByRole('button', { name: 'Page 6' }).click()
  await expect(page.getByTestId('layout-notice')).toHaveText('No text lines for this page')
  await expect(image(page)).toBeVisible()
  await page.getByRole('button', { name: 'Page 7' }).click()
  await expect(page.getByTestId('no-scan')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Zoom in (+)' })).toBeDisabled()

  await openScan(page, letters.id)
  await expect(page.getByTestId('image-pane-text-only')).toBeVisible()
})

test('the viewer works at phone width with touch-sized controls and no horizontal overflow', async ({ page }) => {
  await useViewport(page, 'phone')
  await openScan(page, chronicle.id, PAGE_1)
  await settled(page)
  await expectAligned(page, PAGE_1, 'r002-l001')
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(0)
  for (const name of ['Previous page', 'Next page', 'Zoom in (+)', 'Zoom out (−)', 'Fit the page (0)']) {
    const b = (await page.getByRole('button', { name }).boundingBox())!
    expect(b.x).toBeGreaterThanOrEqual(0)
    expect(b.x + b.width).toBeLessThanOrEqual(390)
  }
  await page.getByRole('button', { name: 'Next page' }).click()
  await expect(page).toHaveURL(new RegExp(`page=${PAGE_2}`))
})
