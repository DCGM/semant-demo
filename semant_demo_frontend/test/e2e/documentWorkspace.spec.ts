import { expect, test, type Locator, type Page } from '@playwright/test'

import {
  answerChat, askChat, chatSource, chunkText, closePhoneNavigation, ensureLoggedIn, fixture, search, useViewport
} from './support'

// The paired document workspace (#545): the public document view (`/documents/:id`) and the
// collection's document view, each with the text/scan correspondence (#544), and the way to
// them from Search and Chat and back. Page fixtures and anchors of the browser-test profile
// (semant_demo_backend/tests/page_fixtures.py): the gazette's chunks are single lines of its
// page 1 (exact anchors); the chronicle's chunk lines differ from the chunk text by a line
// break each (approximate anchors), one chunk continuing from page 1 onto page 2.

const chronicle = fixture.document('chronicle')
const gazette = fixture.document('gazette')
const letters = fixture.document('letters')
const chronicles = fixture.collection('chronicles')
const PAGE_1 = '5e3a0000-0000-4000-8000-0000000d1f01'
const PAGE_2 = '5e3a0000-0000-4000-8000-0000000d1f02'
const GAZETTE_PAGE = fixture.chunk('gazette_1').start_page_id

const position = (page: Page) => page.getByTestId('page-position')
const notice = (page: Page) => page.getByTestId('sync-notice')
const chunk = (page: Page, key: string) => page.locator(`.chunk-annotator[data-chunk-id="${fixture.chunk(key).id}"]`)
const highlights = (page: Page) => page.locator('polygon.scan-highlight')
const overlay = (page: Page) => page.getByTestId('scan-overlay')
const workspace = (page: Page) => page.getByTestId('document-workspace')
const modes = (page: Page) => page.getByTestId('workspace-mode')

/**
 * Waits until an element stops moving: the same box in ten animation frames in a row. After a
 * (re)load the drawers may still be sliding in and narrowing the workspace, and a drag started
 * from a box read meanwhile can miss its target.
 */
async function settled (locator: Locator) {
  await expect.poll(() => locator.evaluate(el => new Promise<boolean>(resolve => {
    const box = () => JSON.stringify(el.getBoundingClientRect())
    const first = box()
    let frames = 0
    const step = () => {
      if (box() !== first) return resolve(false)
      if (++frames === 10) return resolve(true)
      requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }))).toBe(true)
}

/** Clicks the middle of a scan line (the overlay is hit-tested from the layout, not the DOM). */
async function clickLine (page: Page, lineId: string) {
  const b = (await page.locator(`polygon.scan-line[data-line-id="${lineId}"]`).boundingBox())!
  await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2)
}

async function open (page: Page, documentId: string, query = '') {
  await page.goto(`/#/documents/${documentId}${query}`)
  await closePhoneNavigation(page)
  await expect(workspace(page)).toBeAttached()
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

/** The scroll position of the text, which scrolls in its own pane (#600). */
const textScroll = (page: Page) => page.getByTestId('workspace-text').evaluate(el => el.scrollTop)
/** How far the whole page scrolls; the document views fill the window and do not (#600). */
const pageOverflow = (page: Page) => page.evaluate(() => ({
  down: document.documentElement.scrollHeight - window.innerHeight,
  across: document.documentElement.scrollWidth - window.innerWidth
}))
const top = async (page: Page, testId: string) => (await page.getByTestId(testId).boundingBox())!.y
const stageTransform = (page: Page) => page.getByTestId('scan-stage').evaluate(el => getComputedStyle(el).transform)

test.describe('the public document view', () => {
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
    const [text0, scan0] = [await textScroll(page), await stageTransform(page)]

    // Both lines are readable on the fitted page and the short text is in view.
    await clickText(page, 'gazette_2', 3)
    await expect(highlights(page)).toHaveAttribute('data-highlight-line-id', 'r003-l001')
    await clickLine(page, 'r002-l001')
    await expect(chunk(page, 'gazette_1').locator('.is-active-passage')).toHaveText(fixture.chunk('gazette_1').text)
    await page.waitForTimeout(400)
    expect(await textScroll(page)).toBe(text0)
    expect(await stageTransform(page)).toBe(scan0)

    // Zooming and panning the scan, scrolling the text: the other pane stays.
    await page.getByRole('button', { name: 'Zoom in (+)' }).click()
    await page.getByTestId('text-scroll').hover()
    await page.mouse.wheel(0, 200)
    await page.waitForTimeout(400)
    await expect(chunk(page, 'gazette_1').locator('.is-active-passage')).toHaveText(fixture.chunk('gazette_1').text)
    expect(await stageTransform(page)).not.toBe(scan0)
  })

  test('the metadata is in the general sidebar; no collection or annotation data is read', async ({ page }) => {
    await useViewport(page, 'wide')
    const privateReads: string[] = []
    page.on('request', r => {
      if (/\/api\/(tag_spans|user_collections|tags)/.test(r.url())) privateReads.push(r.url())
    })
    await open(page, chronicle.id)
    await expect(page.getByTestId('document-title')).toHaveText(chronicle.properties.title)
    await expect(chunk(page, 'chronicle_1')).toBeVisible()
    // The general right sidebar, with the document's metadata and no collection tools.
    await page.getByRole('listitem', { name: 'Document' }).click()
    await expect(page.getByTestId('right-sidebar-title')).toHaveText('Document')
    await expect(page.locator('[data-sidebar-panel="document-metadata"]')).toContainText('Year issued')
    await expect(page.getByRole('listitem', { name: 'Tags' })).toHaveCount(0)
    // Read-only text: no annotation popover opens on a selection.
    await selectText(page, ['chronicle_1', 0], ['chronicle_1', 8])
    await expect(page.locator('.annotation-popover')).toHaveCount(0)
    // Opened directly: no back link.
    await expect(page.getByRole('link', { name: /^Back to/ })).toHaveCount(0)
    expect(privateReads).toEqual([])
  })

  test('the views: text and scan, text alone, scan alone; a narrow screen shows one of them', async ({ page }) => {
    await useViewport(page, 'wide')
    await open(page, chronicle.id, `?page=${PAGE_1}`)
    await expect(workspace(page)).toHaveAttribute('data-mode', 'split')
    await expect(page.getByTestId('workspace-text')).toBeVisible()
    await expect(page.getByTestId('workspace-scan')).toBeVisible()

    await modes(page).getByRole('button', { name: 'Text', exact: true }).click()
    await expect(page.getByTestId('workspace-scan')).toBeHidden()
    await expect(page).toHaveURL(/view=text/)
    await modes(page).getByRole('button', { name: 'Scan', exact: true }).click()
    await expect(page.getByTestId('workspace-text')).toBeHidden()
    await expect(page.getByTestId('workspace-scan')).toBeVisible()
    // The keyboard of the scan viewer still works on its own.
    await page.getByTestId('scan-viewport').focus()
    await page.keyboard.press('PageDown')
    await expect(position(page)).toHaveText('3 / 7')

    // The link keeps the view; a narrow screen has no room for both.
    await useViewport(page, 'phone')
    await page.reload()
    await closePhoneNavigation(page)
    await expect(workspace(page)).toHaveAttribute('data-mode', 'scan')
    await expect(modes(page).getByRole('button', { name: 'Text and scan' })).toHaveCount(0)
    await modes(page).getByRole('button', { name: 'Text', exact: true }).click()
    await expect(chunk(page, 'chronicle_3')).toBeVisible()
    await expect(page.getByTestId('workspace-scan')).toBeHidden()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  })

  test('pages without text or lines, and a text-only document, keep the text readable', async ({ page }) => {
    await useViewport(page, 'narrow')
    await open(page, chronicle.id, `?page=${PAGE_1}&view=scan`)
    // A page with a scan but no layout, and no chunk on it.
    await page.getByRole('button', { name: 'Page 6' }).click()
    await expect(notice(page)).toHaveText('No document text is known on this page.')
    await modes(page).getByRole('button', { name: 'Text', exact: true }).click()
    await expect(chunk(page, 'chronicle_1')).toBeVisible()

    // A document without scans: the text alone, without a choice of views.
    await open(page, letters.id)
    await expect(workspace(page)).toHaveAttribute('data-mode', 'text')
    await expect(page.getByTestId('workspace-scan')).toBeHidden()
    await expect(modes(page)).toHaveCount(0)
    await expect(chunk(page, 'letters_1')).toBeVisible()
    await clickText(page, 'letters_1', 3)
    await expect(notice(page)).toHaveCount(0)
  })

  test('the reader\'s page change replaces the linked passage in the URL; a reload opens that page', async ({ page }) => {
    await useViewport(page, 'wide')
    const passage = fixture.chunk('chronicle_1')
    await open(page, chronicle.id, `?chunk=${passage.id}&start=0&end=5&from=search`)
    await expect(position(page)).toHaveText('2 / 7')
    await expect(chunk(page, 'chronicle_1').locator('.is-active-passage')).not.toHaveCount(0)
    // The page opened for the passage is not written into the link.
    await expect(page).not.toHaveURL(/page=/)

    await page.getByRole('button', { name: 'Next page' }).click()
    await expect(position(page)).toHaveText('3 / 7')
    await expect(page).toHaveURL(new RegExp(`page=${PAGE_2}`))
    await expect(page).not.toHaveURL(/chunk=|start=|end=/)
    await expect(page).toHaveURL(/from=search/)

    // Reloaded: the page the reader moved to, not the passage of the original link.
    await page.reload()
    await expect(position(page)).toHaveText('3 / 7')
    await expect(chunk(page, 'chronicle_3')).toBeVisible()
    await expect(chunk(page, 'chronicle_1')).toHaveCount(0)
    await expect(page.locator('.is-active-passage')).toHaveCount(0)
  })

  test('another link to the same document shows its passage, page and view without opening it again', async ({ page }) => {
    await useViewport(page, 'wide')
    const first = fixture.chunk('chronicle_1')
    const second = fixture.chunk('chronicle_3')
    await open(page, chronicle.id, `?chunk=${first.id}&start=0&end=5`)
    await expect(position(page)).toHaveText('2 / 7')
    await expect(chunk(page, 'chronicle_1').locator('.is-active-passage')).not.toHaveCount(0)
    const documentReads: string[] = []
    page.on('request', r => { if (new URL(r.url()).pathname === `/api/document/${chronicle.id}`) documentReads.push(r.url()) })
    const follow = (query: string) => page.evaluate((hash) => { location.hash = hash }, `#/documents/${chronicle.id}${query}`)

    // A query-only navigation: the same page shows the new passage and its page.
    const word = second.text.indexOf('polovinu')
    await follow(`?chunk=${second.id}&start=${word}&end=${word + 'polovinu'.length}`)
    await expect(position(page)).toHaveText('3 / 7')
    await expect(chunk(page, 'chronicle_3').locator('.is-active-passage')).toHaveText('polovinu')
    await expect(chunk(page, 'chronicle_1').locator('.is-active-passage')).toHaveCount(0)

    // The view of the link, and the default view of a link without one.
    await follow(`?chunk=${second.id}&start=${word}&end=${word + 'polovinu'.length}&view=text`)
    await expect(workspace(page)).toHaveAttribute('data-mode', 'text')
    await follow(`?page=${PAGE_1}`)
    await expect(workspace(page)).toHaveAttribute('data-mode', 'split')
    await expect(position(page)).toHaveText('2 / 7')
    await expect(page.locator('.is-active-passage')).toHaveCount(0)
    expect(documentReads).toEqual([])
  })

  test('an unknown document says so', async ({ page }) => {
    await useViewport(page, 'wide')
    await page.goto('/#/documents/5e3a0000-0000-4000-8000-00000000dead')
    await expect(page.getByTestId('document-error')).toHaveText('This document is not in the corpus.')
  })
})

test.describe('the layout of the document views (#600)', () => {
  test('the scan left of the text, split by a divider dragged or moved by keys and remembered', async ({ page }) => {
    await useViewport(page, 'wide')
    await open(page, chronicle.id, `?page=${PAGE_1}`)
    await page.evaluate(() => localStorage.removeItem('semant.documentWorkspace.textShare'))
    await page.reload()
    const text = page.getByTestId('workspace-text')
    const scan = page.getByTestId('workspace-scan')
    const divider = page.getByRole('separator', { name: 'Resize the text and the scan' })
    await expect(divider).toHaveAttribute('aria-valuenow', '55')
    expect((await scan.boundingBox())!.x).toBeLessThan((await text.boundingBox())!.x)
    await expect(modes(page).getByRole('button')).toHaveText(['imageScan', 'vertical_splitText and scan', 'articleText'])

    // Dragged 200 px to the left: the text is 200 px wider, the scan 200 px narrower.
    await settled(divider)
    const [text0, scan0] = [(await text.boundingBox())!.width, (await scan.boundingBox())!.width]
    const grip = (await divider.boundingBox())!
    await page.mouse.move(grip.x + grip.width / 2, grip.y + grip.height / 2)
    await page.mouse.down()
    await page.mouse.move(grip.x + grip.width / 2 - 200, grip.y + grip.height / 2, { steps: 5 })
    await page.mouse.up()
    expect((await text.boundingBox())!.width).toBeCloseTo(text0 + 200, -1)
    expect((await scan.boundingBox())!.width).toBeCloseTo(scan0 - 200, -1)

    // The keys: End gives the text its largest width, the scan keeps its minimum.
    await divider.focus()
    await page.keyboard.press('End')
    expect(Math.round((await scan.boundingBox())!.width)).toBe(300)
    await page.keyboard.press('ArrowRight')
    const chosen = await divider.getAttribute('aria-valuenow')
    await page.reload()
    await expect(divider).toHaveAttribute('aria-valuenow', chosen!)
    // A double click resets the split.
    await divider.dblclick()
    await expect(divider).toHaveAttribute('aria-valuenow', '55')
  })

  test('a one-row header with the long title cut; the page does not scroll, the panes do', async ({ page }) => {
    const title = 'St. Petersburgische Zeitung. Ein sehr langer Titel einer Zeitung mit Beilagen, '.repeat(3).trim()
    await page.route(`**/api/document/${chronicle.id}`, async (route) => {
      const response = await route.fetch()
      await route.fulfill({ response, json: { ...(await response.json()), title } })
    })
    // A short window: the scan's controls and thumbnails stay in it.
    await page.setViewportSize({ width: 1920, height: 560 })
    await open(page, chronicle.id, `?page=${PAGE_1}`)
    const header = page.getByTestId('document-header')
    await expect(page.getByTestId('document-title')).toHaveText(title)
    expect((await header.boundingBox())!.height).toBe(48)
    // The whole title is in the tooltip of the cut one.
    expect(await page.getByTestId('document-title').locator('..').getAttribute('title')).toContain(title)
    expect(await page.getByTestId('document-title').evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true)
    expect(await pageOverflow(page)).toEqual({ down: 0, across: 0 })
    for (const name of ['Previous page', 'Fit the page (0)']) {
      await expect(page.getByRole('button', { name })).toBeInViewport()
    }
    await expect(page.getByRole('button', { name: 'Page 6' })).toBeInViewport()

    // On a short phone screen the (whole, short) fixture text is longer than its pane: it
    // scrolls, the header and controls stay.
    await page.setViewportSize({ width: 390, height: 320 })
    await modes(page).getByRole('button', { name: 'Text', exact: true }).click()
    await page.getByTestId('text-later').click()
    await expect(chunk(page, 'chronicle_3')).toBeAttached()
    const text = page.getByTestId('workspace-text')
    await expect.poll(() => text.evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true)
    const [header0, controls0] = [await top(page, 'document-header'), await top(page, 'workspace-controls')]
    await text.hover()
    await page.mouse.wheel(0, 300)
    await expect.poll(() => textScroll(page)).toBeGreaterThan(0)
    expect(await top(page, 'document-header')).toBe(header0)
    expect(await top(page, 'workspace-controls')).toBe(controls0)
    expect(await pageOverflow(page)).toEqual({ down: 0, across: 0 })
  })

  test('the public view collapses and restores the whitespace, as the collection reader does', async ({ page }) => {
    await useViewport(page, 'wide')
    await open(page, letters.id)
    const text = page.locator('.document-text')
    const toggle = page.getByRole('button', { name: 'Original whitespace' })
    await expect(text).toHaveClass(/document-text--preserve-whitespace/)
    await expect(toggle).toHaveAttribute('aria-pressed', 'true')
    await toggle.click()
    await expect(text).not.toHaveClass(/document-text--preserve-whitespace/)
    await expect(toggle).toHaveAttribute('aria-pressed', 'false')
    // A text-only document: the toggle, without a choice of views.
    await expect(modes(page)).toHaveCount(0)
  })

  test('the collection reader\'s controls stay above the text while it scrolls (#588)', async ({ page }) => {
    await ensureLoggedIn(page, 'owner')
    await page.setViewportSize({ width: 390, height: 400 })
    await page.goto(`/#/collections/${chronicles.id}/documents/${chronicle.id}/v1?view=text`)
    await closePhoneNavigation(page)
    await expect(chunkText(page, 'chronicle_1')).toBeVisible()
    const text = page.getByTestId('workspace-text')
    await expect.poll(() => text.evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true)
    const controls = page.getByTestId('workspace-controls')
    const before = (await controls.boundingBox())!
    await text.hover()
    await page.mouse.wheel(0, 300)
    await expect.poll(() => textScroll(page)).toBeGreaterThan(0)
    expect((await controls.boundingBox())!).toEqual(before)
    await expect(page.getByRole('button', { name: 'Original whitespace' })).toBeInViewport()
    await expect(controls.getByRole('button', { name: 'All chunks' })).toBeInViewport()
    expect(await pageOverflow(page)).toEqual({ down: 0, across: 0 })
  })
})

test.describe('from Search and Chat and back', () => {
  test('a search result opens its document and the search is there on return', async ({ page }) => {
    await useViewport(page, 'wide')
    await search(page, 'Lhota')
    const target = fixture.chunk('chronicle_2')
    const card = page.locator('.search-result', { hasText: target.text }).first()
    await card.getByRole('button', { name: /in its document$/ }).click()
    const context = page.getByTestId('chunk-context')
    await expect(context.locator('[aria-current="true"]')).toHaveText(new RegExp(target.text))
    // The side panel is the passage; the full view is a separate, explicit step.
    await context.getByTestId('chunk-context-open').click()
    await expect(page).toHaveURL(new RegExp(`/documents/${chronicle.id}\\?chunk=${target.id}&from=search`))
    await expect(chunk(page, 'chronicle_2')).toBeVisible()
    await expect(overlay(page)).toHaveAttribute('data-layout-page-id', PAGE_1)
    await expect(page.getByRole('listitem', { name: 'Summary' })).toHaveCount(0)

    // Back: the same results, the opened result still in its panel.
    await page.getByRole('link', { name: 'Back to search results' }).click()
    await expect(page).toHaveURL(/#\/search/)
    await expect(page.getByRole('combobox', { name: 'Search query' })).toHaveValue('Lhota')
    await expect(page.locator('.search-result', { hasText: target.text }).first()).toBeVisible()
    await expect(page.getByTestId('right-sidebar-title')).toHaveText('Document')
    await expect(context.locator('[aria-current="true"]')).toHaveText(new RegExp(target.text))

    // The browser's back and forward work too.
    await page.goBack()
    await expect(chunk(page, 'chronicle_2')).toBeVisible()
    await page.goBack()
    await expect(page.locator('.search-result', { hasText: target.text }).first()).toBeVisible()
    // Escape on the search page acts there again (and not while the document was shown).
    await card.getByRole('checkbox').click()
    await expect(page.locator('.selection-toolbar')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.locator('.selection-toolbar')).toBeHidden()
  })

  test('a chat source opens its document and the conversation is there on return', async ({ page }) => {
    await useViewport(page, 'wide')
    await answerChat(page, [{ rag_answer: 'The arrival [doc 1].', sources: [chatSource('chronicle_3')] }])
    await page.goto('/#/rag')
    await closePhoneNavigation(page)
    await askChat(page, 'Who arrived?')
    await page.locator('.message-bubble').getByRole('link', { name: '[S1]' }).dblclick()
    await page.getByTestId('chunk-context').getByTestId('chunk-context-open').click()
    await expect(page).toHaveURL(/from=chat/)
    await expect(chunk(page, 'chronicle_3')).toBeVisible()
    await expect(overlay(page)).toHaveAttribute('data-layout-page-id', PAGE_2)

    await page.getByRole('link', { name: 'Back to the conversation' }).click()
    await expect(page.locator('.message-bubble', { hasText: 'Who arrived?' })).toBeVisible()
    await expect(page.locator('.message-bubble', { hasText: 'The arrival' })).toBeVisible()
    await expect(page.getByTestId('chunk-context').locator('[aria-current="true"]')).toHaveText(new RegExp(fixture.chunk('chronicle_3').text))
  })
})

test.describe('the collection document view', () => {
  const collectionUrl = (query = '') => `/#/collections/${chronicles.id}/documents/${chronicle.id}/v1${query}`

  test('shows the scan beside the annotated text, synchronized, with the collection tools', async ({ page }) => {
    await useViewport(page, 'wide')
    await ensureLoggedIn(page, 'owner')
    await page.goto(collectionUrl(`?page=${PAGE_2}`))
    await expect(workspace(page)).toHaveAttribute('data-mode', 'split')
    await expect(position(page)).toHaveText('3 / 7')
    await expect(chunkText(page, 'chronicle_3')).toBeVisible()
    // Annotations and the collection's panels are as before.
    await expect(chunkText(page, 'chronicle_1').locator('.text-segment.is-tagged').first()).toBeVisible()
    for (const name of ['Tags', 'AI Tagging', 'Summary', 'Document']) {
      await expect(page.getByRole('listitem', { name })).toHaveCount(1)
    }

    // Scan to text, and text to scan.
    await clickLine(page, 'r001-l001')
    await expect(chunkText(page, 'chronicle_2').locator('.is-active-passage')).not.toHaveCount(0)
    await clickText(page, 'chronicle_1', 3)
    await expect(overlay(page)).toHaveAttribute('data-layout-page-id', PAGE_1)
    await expect(highlights(page)).toHaveAttribute('data-highlight-line-id', 'r002-l001')

    // A selection still opens the annotation popover, and shows its lines on the scan.
    await selectText(page, ['chronicle_1', 0], ['chronicle_1', 8])
    await expect(page.locator('.annotation-popover')).toBeVisible()
    await expect(highlights(page)).toHaveAttribute('data-highlight-line-id', 'r002-l001')
    await page.keyboard.press('Escape')

    // Text only: the reader as before.
    await modes(page).getByRole('button', { name: 'Text', exact: true }).click()
    await expect(page.getByTestId('workspace-scan')).toBeHidden()
    await expect(chunkText(page, 'chronicle_1')).toBeVisible()
  })

  test('the reader\'s page change replaces the linked annotation in the URL; a reload opens that page', async ({ page }) => {
    await useViewport(page, 'wide')
    await ensureLoggedIn(page, 'owner')
    const novak = fixture.span('novak_manual')
    await page.goto(collectionUrl(`?annotation=${novak.id}&chunk=${fixture.chunk('chronicle_1').id}`))
    // The annotation's page, opened for the text: not written into the link.
    await expect(position(page)).toHaveText('2 / 7')
    await expect(page).not.toHaveURL(/page=/)

    await page.getByRole('button', { name: 'Next page' }).click()
    await expect(position(page)).toHaveText('3 / 7')
    await expect(page).toHaveURL(new RegExp(`page=${PAGE_2}`))
    await expect(page).not.toHaveURL(/annotation=|chunk=|order=/)

    await page.reload()
    await expect(position(page)).toHaveText('3 / 7')
    await expect(chunk(page, 'chronicle_3').locator('.is-current-page')).not.toHaveCount(0)
  })

  test('a page change while the text is still loading is followed, not the page shown first', async ({ page }) => {
    await useViewport(page, 'wide')
    await ensureLoggedIn(page, 'owner')
    // The collection's chunks of the document arrive only once the reader moved on in the scan.
    let release: () => void = () => undefined
    const released = new Promise<void>(resolve => { release = resolve })
    await page.route(new RegExp(`/api/user_collections/${chronicles.id}/documents/${chronicle.id}/chunks(\\?|$)`), async (route) => {
      await released
      await route.continue()
    })
    await page.goto(collectionUrl(`?page=${PAGE_1}`))
    await expect(position(page)).toHaveText('2 / 7')
    await page.getByRole('button', { name: 'Next page' }).click()
    await expect(position(page)).toHaveText('3 / 7')
    // Still no text of the collection.
    await expect(chunk(page, 'chronicle_1')).toHaveCount(0)
    release()

    await expect(chunk(page, 'chronicle_3').locator('.is-current-page')).not.toHaveCount(0)
    await expect(chunk(page, 'chronicle_1').locator('.is-current-page')).toHaveCount(0)
    await expect(position(page)).toHaveText('3 / 7')
  })

  test('a collection the user cannot open says so and leads to the public document', async ({ page }) => {
    await useViewport(page, 'wide')
    await ensureLoggedIn(page, 'outsider')
    await page.goto(collectionUrl())
    const banner = page.getByTestId('collection-unavailable')
    await expect(banner).toContainText('not shared with you')
    await banner.getByRole('link', { name: 'Open the public document' }).click()
    await expect(page).toHaveURL(new RegExp(`/documents/${chronicle.id}$`))
    await expect(chunk(page, 'chronicle_1')).toBeVisible()
  })
})
