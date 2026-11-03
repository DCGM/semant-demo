import { expect, test, type Page } from '@playwright/test'

import { closePhoneNavigation, fixture, useViewport } from './support'

// The text/scan correspondence (#544) on its preview page, with the page fixtures and
// anchors of the browser-test profile (semant_demo_backend/tests/page_fixtures.py): the
// gazette's chunks are single lines of its page 1 (exact anchors); the chronicle's chunk
// lines differ from the chunk text by a line break each (approximate anchors), one chunk
// continuing from page 1 onto page 2.

const chronicle = fixture.document('chronicle')
const gazette = fixture.document('gazette')
const letters = fixture.document('letters')
const PAGE_1 = '5e3a0000-0000-4000-8000-0000000d1f01'
const PAGE_2 = '5e3a0000-0000-4000-8000-0000000d1f02'
const GAZETTE_PAGE = fixture.chunk('gazette_1').start_page_id

const position = (page: Page) => page.getByTestId('page-position')
const notice = (page: Page) => page.getByTestId('sync-notice')
const chunk = (page: Page, key: string) => page.locator(`.chunk-annotator[data-chunk-id="${fixture.chunk(key).id}"]`)
const highlights = (page: Page) => page.locator('polygon.scan-highlight')
const overlay = (page: Page) => page.getByTestId('scan-overlay')

/** Clicks the middle of a scan line (the overlay is hit-tested from the layout, not the DOM). */
async function clickLine (page: Page, lineId: string) {
  const b = (await page.locator(`polygon.scan-line[data-line-id="${lineId}"]`).boundingBox())!
  await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2)
}

async function open (page: Page, documentId: string, query = '') {
  await page.goto(`/#/preview/text-scan/${documentId}${query}`)
  await closePhoneNavigation(page)
  await expect(page.getByTestId('document-image-pane')).toBeVisible()
}

/** Clicks the text of a chunk at a UTF-16 offset, as a reader placing the caret there. */
async function clickText (page: Page, key: string, offset: number) {
  const point = await chunk(page, key).evaluate((el, at) => {
    for (const seg of Array.from(el.querySelectorAll<HTMLElement>('.text-segment'))) {
      const start = Number(seg.dataset.start)
      if (Number(seg.dataset.end) <= at) continue
      const node = Array.from(seg.childNodes).find(n => n.nodeType === Node.TEXT_NODE)!
      const range = document.createRange()
      range.setStart(node, at - start)
      range.setEnd(node, at - start + 1)
      const r = range.getClientRects()[0]
      return { x: r.left + r.width / 2, y: r.top + r.height / 2 }
    }
    throw new Error('offset not in the chunk')
  }, offset)
  await page.mouse.click(point.x, point.y)
}

/** Selects the text between two chunk offsets and releases the button, as a drag would. */
async function selectText (page: Page, from: [string, number], to: [string, number]) {
  const ids = [fixture.chunk(from[0]).id, fixture.chunk(to[0]).id]
  await page.evaluate(([[a, aOffset], [b, bOffset]]) => {
    const nodeAt = (id: string, at: number): [Node, number] => {
      const chunkEl = document.querySelector(`.chunk-annotator[data-chunk-id="${id}"]`)!
      for (const seg of Array.from(chunkEl.querySelectorAll<HTMLElement>('.text-segment'))) {
        if (Number(seg.dataset.end) < at) continue
        return [Array.from(seg.childNodes).find(n => n.nodeType === Node.TEXT_NODE)!, at - Number(seg.dataset.start)]
      }
      throw new Error('offset not in the chunk')
    }
    const range = document.createRange()
    range.setStart(...nodeAt(a as string, aOffset as number))
    range.setEnd(...nodeAt(b as string, bOffset as number))
    window.getSelection()!.removeAllRanges()
    window.getSelection()!.addRange(range)
    document.querySelector('.document-text')!.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
  }, [[ids[0], from[1]], [ids[1], to[1]]])
}

const scrollTop = (page: Page) => page.getByTestId('text-scroll').evaluate(el => el.scrollTop)
const stageTransform = (page: Page) => page.getByTestId('scan-stage').evaluate(el => getComputedStyle(el).transform)

test('a deep-linked passage opens its page and exact words; a scan line selects its exact text', async ({ page }) => {
  await useViewport(page, 'wide')
  const passage = fixture.chunk('gazette_1')
  const word = passage.text.indexOf('hostila')
  await open(page, gazette.id, `?chunk=${passage.id}&start=${word}&end=${word + 'hostila'.length}`)

  // The scan opens the passage's page (the 2nd of 120) and highlights its word, exactly.
  await expect(position(page)).toHaveText('2 / 120')
  await expect(overlay(page)).toHaveAttribute('data-layout-page-id', GAZETTE_PAGE)
  await expect(highlights(page)).toHaveCount(1)
  await expect(highlights(page)).toHaveAttribute('data-highlight-line-id', 'r002-l001')
  await expect(highlights(page)).not.toHaveClass(/approximate/)
  await expect(chunk(page, 'gazette_1').locator('.is-active-passage')).toHaveText('hostila')
  await expect(notice(page)).toHaveCount(0)

  // Clicking the other chunk's line on the scan selects its text, exactly.
  await clickLine(page, 'r003-l001')
  await expect(chunk(page, 'gazette_2').locator('.is-active-passage')).toHaveText(fixture.chunk('gazette_2').text)
  await expect(page.locator('.has-approximate-passage')).toHaveCount(0)
  // The current page is tinted in the text; the page start is marked outside the text.
  await expect(chunk(page, 'gazette_2').locator('.is-current-page')).toHaveText(fixture.chunk('gazette_2').text)
  await expect(chunk(page, 'gazette_1').locator('.page-break')).toHaveCount(0)
})

test('a page opens with its text alone; approximate lines are whole lines, marked as such', async ({ page }) => {
  await useViewport(page, 'wide')
  const layouts: string[] = []
  const pageReads: string[] = []
  page.on('request', r => {
    if (r.url().endsWith('/layout')) layouts.push(r.url())
    if (r.url().includes('/chunks/by_page')) pageReads.push(new URL(r.url()).searchParams.get('page')!)
  })
  await open(page, chronicle.id, `?page=${PAGE_2}`)
  await expect(position(page)).toHaveText('3 / 7')
  // The text of page 2: the chunk continuing from page 1 and the chunk on page 2.
  await expect(chunk(page, 'chronicle_3')).toBeVisible()
  await expect(chunk(page, 'chronicle_2')).toBeVisible()
  await expect(chunk(page, 'chronicle_1')).toHaveCount(0)
  // Where page 2 begins inside the continuing chunk, approximately.
  await expect(chunk(page, 'chronicle_2').locator('.page-break')).toHaveAttribute('aria-label', 'Page 2 (approximate position)')

  // A click on a page 2 line of the continuing chunk: its text, approximate.
  await clickLine(page, 'r001-l001')
  await expect(chunk(page, 'chronicle_2').locator('.is-active-passage')).not.toHaveCount(0)
  await expect(page.locator('.has-approximate-passage')).toHaveCount(1)
  await expect(notice(page)).toContainText('its place in the text is approximate')

  // A click in the text: the scan highlights the whole line, dashed, and says so.
  const text = fixture.chunk('chronicle_3').text
  await clickText(page, 'chronicle_3', text.indexOf('polovinu') + 2)
  await expect(highlights(page)).toHaveCount(1)
  await expect(highlights(page)).toHaveAttribute('data-highlight-line-id', 'r002-l002')
  await expect(highlights(page)).toHaveClass(/scan-highlight--approximate/)
  await expect(notice(page)).toContainText('whole lines are shown')

  // Only the layouts and page reads needed: pages 1 and 2, never the whole document.
  expect(new Set(layouts.map(u => u.split('/pages/')[1].split('/')[0]))).toEqual(new Set([PAGE_1, PAGE_2]))
  expect(pageReads).toEqual(['2'])
})

test('a selection across pages highlights every line and focuses only its beginning', async ({ page }) => {
  await useViewport(page, 'wide')
  await open(page, chronicle.id, `?chunk=${fixture.chunk('chronicle_1').id}`)
  await expect(position(page)).toHaveText('2 / 7')
  await expect(chunk(page, 'chronicle_2')).toBeVisible()
  const second = fixture.chunk('chronicle_2').text
  await selectText(page, ['chronicle_1', 5], ['chronicle_2', second.length - 2])
  // The selection begins on page 1, which stays shown, with its lines highlighted.
  await expect(position(page)).toHaveText('2 / 7')
  await expect(overlay(page)).toHaveAttribute('data-layout-page-id', PAGE_1)
  await expect.poll(() => highlights(page).evaluateAll(els => els.map(e => e.getAttribute('data-highlight-line-id'))))
    .toEqual(['r002-l001', 'r002-l002', 'r002-l003', 'r003-l001', 'r003-l002'])
  // The rest is on page 2: shown there when the reader goes on.
  await page.getByRole('button', { name: 'Next page' }).click()
  await expect(overlay(page)).toHaveAttribute('data-layout-page-id', PAGE_2)
  await expect(highlights(page)).toHaveAttribute('data-highlight-line-id', 'r001-l001')
})

test('smart focus: a visible target moves neither pane, and scrolling is never followed', async ({ page }) => {
  await useViewport(page, 'wide')
  await open(page, gazette.id, `?page=${GAZETTE_PAGE}`)
  await expect(chunk(page, 'gazette_2')).toBeVisible()
  await expect(overlay(page)).toBeAttached()
  await page.waitForTimeout(400)
  const [text0, scan0] = [await scrollTop(page), await stageTransform(page)]

  // Both lines are readable on the fitted page and the short text is in view.
  await clickText(page, 'gazette_2', 3)
  await expect(highlights(page)).toHaveAttribute('data-highlight-line-id', 'r003-l001')
  await clickLine(page, 'r002-l001')
  await expect(chunk(page, 'gazette_1').locator('.is-active-passage')).toHaveText(fixture.chunk('gazette_1').text)
  await page.waitForTimeout(400)
  expect(await scrollTop(page)).toBe(text0)
  expect(await stageTransform(page)).toBe(scan0)

  // Zooming and panning the scan, scrolling the text: the other pane stays.
  await page.getByRole('button', { name: 'Zoom in (+)' }).click()
  await page.getByTestId('text-scroll').hover()
  await page.mouse.wheel(0, 200)
  await page.waitForTimeout(400)
  expect(await scrollTop(page)).toBe(text0)
  await expect(chunk(page, 'gazette_1').locator('.is-active-passage')).toHaveText(fixture.chunk('gazette_1').text)
})

test('pages without text or lines, and a text-only document, keep the text readable', async ({ page }) => {
  await useViewport(page, 'narrow')
  await open(page, chronicle.id, `?page=${PAGE_1}`)
  await expect(chunk(page, 'chronicle_1')).toBeVisible()
  // A page with a scan but no layout, and no chunk on it.
  await page.getByRole('button', { name: 'Page 6' }).click()
  await expect(notice(page)).toHaveText('No document text is known on this page.')
  await expect(chunk(page, 'chronicle_1')).toBeVisible()

  await open(page, letters.id)
  await expect(page.getByTestId('image-pane-text-only')).toBeVisible()
  await expect(chunk(page, 'letters_1')).toBeVisible()
  await clickText(page, 'letters_1', 3)
  await expect(notice(page)).toHaveCount(0)
})
