import { readFileSync } from 'fs'
import { expect, test, type APIRequestContext, type Download, type Locator, type Page } from '@playwright/test'

import { apiToken, deleteAddedSpans, ensureLoggedIn, fixture, sidebarPanelButton, useViewport, viewports } from './support'
import { animatedPart, longDocument, recordScroll } from './longDocument'

// The collection's annotation workspace (#329): one aligned line per annotation (KWIC),
// filters, distinct selection and source context in the shared right sidebar, and the
// workspace kept while a document is opened. Selection and review (#459): "all matches" is
// a fixed set of ids, hidden members are counted, and reviews report each annotation.
// Provenance and edit conflicts (#460): the sidebar names who created and changed the open
// annotation, and a review of an annotation someone else changed meanwhile is refused.

const chronicles = fixture.collection('chronicles')
const rows = (page: Page) => page.getByTestId('kwic-row')
const row = (page: Page, text: string) => rows(page).filter({ has: page.locator('.kwic__key', { hasText: text }) })
const panel = (page: Page) => page.getByTestId('chunk-context')

async function openWorkspace (page: Page, userKey = 'owner') {
  await ensureLoggedIn(page, userKey)
  await page.goto(`/#/collections/${chronicles.id}/annotations`)
  await expect(page.getByTestId('concordance-range')).toContainText('matching annotations')
}

/** Creates a confirmed span through the API (removed again by `deleteAddedSpans`). */
async function createSpan (request: APIRequestContext, chunkKey: string, start: number, end: number) {
  const response = await request.post('/api/tag_spans', {
    headers: { Authorization: `Bearer ${await apiToken(request, 'owner')}` },
    data: { chunkId: fixture.chunk(chunkKey).id, tagId: fixture.tag('person').id, start, end, type: 'pos' }
  })
  expect(response.ok()).toBe(true)
  expect((await response.json()).outcome).toBe('complete')
}

/** Patches a seeded span as the document view's editor would. */
async function patchSpan (request: APIRequestContext, spanId: string, data: Record<string, unknown>, userKey = 'owner') {
  const response = await request.patch(`/api/tag_spans/${spanId}`, {
    headers: { Authorization: `Bearer ${await apiToken(request, userKey)}` },
    params: { collection_id: chronicles.id },
    data
  })
  expect(response.ok()).toBe(true)
}

test.afterEach(async ({ request }) => {
  await deleteAddedSpans(request, 'owner', 'chronicles')
})

test('one aligned line per annotation; rejected ones only on request', async ({ page }) => {
  await useViewport(page, 'wide')
  await openWorkspace(page)

  // Confirmed and proposals by default: Novák, Lhoty, Brně, Prahy; the rejected Kronikář is not shown.
  await expect(rows(page)).toHaveCount(4)
  await expect(page.getByTestId('concordance-range')).toHaveText('Rows 1–4 of 4 matching annotations')
  await expect(row(page, 'Kronikář')).toHaveCount(0)
  await expect(row(page, 'Lhoty')).toContainText('Proposal')
  await expect(row(page, 'Jan Novák')).toContainText('Confirmed')
  await expect(row(page, 'Jan Novák')).toContainText(`${fixture.document('chronicle').properties.yearIssued}`)

  const keys = await rows(page).locator('.kwic__key').evaluateAll(els => els.map(e => e.getBoundingClientRect()))
  expect(Math.max(...keys.map(k => k.height)), 'every row is one line').toBeLessThan(40)
  // Each annotation is centered under the Annotation header, whatever its length; the contexts
  // run right up to it from both sides (#665).
  const head = (await page.getByTestId('kwic-head-annotation').boundingBox())!
  for (const k of keys) expect(Math.abs(k.left + k.width / 2 - (head.x + head.width / 2)), 'centered').toBeLessThanOrEqual(1.5)
  const parts = await rows(page).first().getByTestId('kwic-text').evaluate(el =>
    ['.kwic__left', '.kwic__key', '.kwic__right'].map(s => el.querySelector(s)!.getBoundingClientRect()))
  expect(Math.abs(parts[0].right - parts[1].left), 'no gap before').toBeLessThanOrEqual(0.5)
  expect(Math.abs(parts[2].left - parts[1].right), 'no gap after').toBeLessThanOrEqual(0.5)
  expect(Math.abs(parts[0].width - parts[2].width), 'equal context boxes').toBeLessThanOrEqual(1)
  // Left context ends at the annotation, right context starts after it.
  await expect(row(page, 'Jan Novák').locator('.kwic__left')).toContainText('hejtman')
  await expect(row(page, 'Jan Novák').locator('.kwic__right')).toContainText('a ubytoval')

  await page.getByTestId('concordance-status-neg').click()
  await expect(row(page, 'Kronikář')).toContainText('Rejected')
  await expect(rows(page)).toHaveCount(5)
})

test('opening, checking and keyboard use are distinct; the source shows the exact span', async ({ page }) => {
  await useViewport(page, 'narrow')
  await openWorkspace(page)

  // Checking a row does not open its source.
  await row(page, 'Prahy').getByRole('checkbox').click()
  await expect(page.getByTestId('concordance-selected')).toHaveText('1 selected')
  await expect(sidebarPanelButton(page, 'Annotation')).toHaveCount(0)

  // Clicking a row opens it in the shared sidebar without checking it.
  await row(page, 'Jan Novák').click()
  await expect(page.getByTestId('right-sidebar-title')).toHaveText('Annotation')
  await expect(panel(page).getByTestId('chunk-context-mark')).toHaveText('Jan Novák')
  await expect(panel(page).getByTestId('chunk-context-header')).toContainText(fixture.document('chronicle').properties.title)
  await expect(panel(page).getByTestId('annotation-context-text')).toHaveText('Jan Novák')
  await expect(row(page, 'Jan Novák')).toHaveAttribute('aria-selected', 'false')
  await expect(row(page, 'Jan Novák')).toHaveAttribute('aria-current', 'true')

  // Keyboard: arrows move, Space checks, Enter opens.
  await row(page, 'Jan Novák').focus()
  await page.keyboard.press('ArrowDown')
  const keys = await rows(page).locator('.kwic__key-label').allTextContents()
  const next = rows(page).nth(keys.indexOf('Jan Novák') + 1)
  await expect(next).toBeFocused()
  await page.keyboard.press('Space')
  await expect(page.getByTestId('concordance-selected')).toHaveText('2 selected')
  await page.keyboard.press('Enter')
  await expect(next).toHaveAttribute('aria-current', 'true')
  await expect(panel(page).getByTestId('chunk-context-mark')).toHaveText(await next.locator('.kwic__key-label').textContent() ?? '')
})

test('switching between annotations of one document keeps the passage in place', async ({ page }) => {
  // Regression (#493): every switch blanked the Document panel and read the passage again.
  await useViewport(page, 'wide')
  await openWorkspace(page)
  const windowReads: string[] = []
  page.on('request', r => { if (/\/api\/documents\/[^/]+\/chunks\/[^/]+\/window/.test(r.url())) windowReads.push(r.url()) })

  await row(page, 'Jan Novák').click()
  await expect(panel(page).getByTestId('chunk-context-mark')).toHaveText('Jan Novák')
  expect(windowReads).toHaveLength(1)

  // Record whether the passage ever disappears while switching.
  await panel(page).evaluate(el => {
    const w = window as unknown as { passageEmptied: boolean }
    w.passageEmptied = false
    new MutationObserver(() => {
      if (!el.querySelector('.chunk-context__chunk')) w.passageEmptied = true
    }).observe(el, { childList: true, subtree: true })
  })

  // Brně is in the next chunk of the same chronicle, already in the shown passage.
  await row(page, 'Brně').click()
  await expect(panel(page).getByTestId('annotation-context-text')).toHaveText('Brně')
  await expect(panel(page).getByTestId('chunk-context-mark')).toHaveText('Brně')
  await expect(panel(page).locator('[aria-current="true"]')).toHaveAttribute('data-chunk-id', fixture.chunk('chronicle_2').id)
  await row(page, 'Jan Novák').click()
  await expect(panel(page).getByTestId('chunk-context-mark')).toHaveText('Jan Novák')
  expect(windowReads, 'no passage read within the shown passage').toHaveLength(1)
  expect(await page.evaluate(() => (window as unknown as { passageEmptied: boolean }).passageEmptied)).toBe(false)

  // Another document is read as before.
  await row(page, 'Prahy').click()
  await expect(panel(page).getByTestId('chunk-context-mark')).toHaveText('Prahy')
  await expect(panel(page).getByTestId('chunk-context-header')).toContainText(fixture.document('letters').properties.title)
  expect(windowReads).toHaveLength(2)
})

test.describe('switching annotations of one long document', () => {
  // #493: the motion shows whether the other annotation is earlier or later, and a long
  // distance is jumped over instead of animated. The chronicle is answered as 40 long
  // paragraphs (longDocument): Jan Novák in paragraph 2, Brně further on.
  const novak = fixture.chunk('chronicle_1').id
  const brno = fixture.chunk('chronicle_2').id
  const mark = (page: Page) => panel(page).getByTestId('chunk-context-mark')

  /** At most one instant jump, and the animated rest covers less than a screen. */
  function expectShortMotion (trace: number[], screen: number, direction: 1 | -1) {
    const steps = trace.slice(1).map((top, i) => top - trace[i])
    expect(steps.filter(step => Math.abs(step) > screen / 2).length, `one jump at most: ${trace.join(' ')}`).toBeLessThanOrEqual(1)
    const { from, to } = animatedPart(trace, screen / 2)
    expect(Math.sign(to - from), `animated ${direction > 0 ? 'down' : 'up'}: ${trace.join(' ')}`).toBe(direction)
    expect(Math.abs(to - from), `only the lead-in is animated: ${trace.join(' ')}`).toBeLessThan(screen)
  }

  test('within the shown passage: later scrolls down, earlier up, far apart jumps', async ({ page }) => {
    const reads = await longDocument(page, { length: 40, placed: { [novak]: 2, [brno]: 20 } })
    await useViewport(page, 'wide')
    await openWorkspace(page)
    await row(page, 'Jan Novák').click()
    await expect(mark(page)).toHaveText('Jan Novák')
    // Read on until Brně is in the passage (paragraphs 0–25).
    for (let i = 0; i < 4; i++) {
      await panel(page).getByRole('button', { name: 'Show later text' }).click()
      await expect(panel(page).getByRole('button', { name: 'Show later text' })).toBeEnabled()
    }
    await expect(panel(page).locator(`[data-chunk-id="${brno}"]`)).toHaveCount(1)
    const screen = await (await recordScroll(panel(page))).height()
    // Back at Jan Novák (extending left the passage at its end).
    await mark(page).evaluate(el => el.scrollIntoView({ block: 'center' }))
    await expect(mark(page)).toBeInViewport()

    let trace = await recordScroll(panel(page))
    await row(page, 'Brně').click()
    await expect(mark(page)).toHaveText('Brně')
    let path = await trace.stop()
    expect(path[path.length - 1], 'Brně is far below').toBeGreaterThan(path[0] + screen)
    expectShortMotion(path, screen, 1)
    await expect(mark(page)).toBeInViewport()

    trace = await recordScroll(panel(page))
    await row(page, 'Jan Novák').click()
    await expect(mark(page)).toHaveText('Jan Novák')
    path = await trace.stop()
    expect(path[path.length - 1]).toBeLessThan(path[0] - screen)
    expectShortMotion(path, screen, -1)
    await expect(mark(page)).toBeInViewport()
    expect(reads.window, 'no passage read within the shown passage').toBe(1)
  })

  test('outside the shown passage: the old text stays while loading, the new one comes in from its side', async ({ page }) => {
    const reads = await longDocument(page, { length: 40, placed: { [novak]: 2, [brno]: 30 }, delay: 800 })
    await useViewport(page, 'wide')
    await openWorkspace(page)
    await row(page, 'Jan Novák').click()
    await expect(mark(page)).toHaveText('Jan Novák')
    const screen = await (await recordScroll(panel(page))).height()

    let trace = await recordScroll(panel(page))
    await row(page, 'Brně').click()
    // The previous passage (paragraphs 0–5) stays while paragraphs 27–33 load.
    await expect(panel(page).getByTestId('chunk-context-reloading')).toBeVisible()
    await expect(panel(page).locator('.chunk-context__chunk').first()).toContainText('[Paragraph 0]')
    await expect(panel(page)).not.toContainText('Loading the document…')
    await expect(panel(page).getByRole('button', { name: 'Show later text' })).toBeDisabled()
    await expect(mark(page)).toHaveText('Brně')
    await expect(panel(page).getByTestId('chunk-context-reloading')).toHaveCount(0)
    let path = await trace.stop()
    expectShortMotion(path, screen, 1)
    await expect(mark(page)).toBeInViewport()

    trace = await recordScroll(panel(page))
    await row(page, 'Jan Novák').click()
    await expect(mark(page)).toHaveText('Jan Novák')
    path = await trace.stop()
    expectShortMotion(path, screen, -1)
    await expect(mark(page)).toBeInViewport()
    expect(reads.window).toBe(3)
  })

  test('an annotation at the end of a tall paragraph is scrolled into view', async ({ page }) => {
    // Regression: the panel showed the start of a tall paragraph, its annotation below the screen.
    await longDocument(page, { length: 40, placed: { [novak]: 2, [brno]: 30 }, lead: { [brno]: 12 } })
    await useViewport(page, 'wide')
    await openWorkspace(page)
    await row(page, 'Jan Novák').click()
    await expect(mark(page)).toHaveText('Jan Novák')
    await row(page, 'Brně').click()
    await expect(mark(page)).toHaveText('Brně')
    const tall = await panel(page).locator(`[data-chunk-id="${brno}"]`).evaluate(el => el.getBoundingClientRect().height)
    expect(tall, 'the paragraph is taller than the screen').toBeGreaterThan(1000)
    await expect(mark(page)).toBeInViewport()
  })

  test('only the passage scrolls: the annotation above it stays in place (#659)', async ({ page }) => {
    await longDocument(page, { length: 40, placed: { [novak]: 2, [brno]: 30 } })
    for (const width of ['wide', 'phone'] as const) {
      await useViewport(page, width)
      await openWorkspace(page)
      await row(page, 'Brně').click()
      await expect(mark(page)).toHaveText('Brně')
      await expect(mark(page)).toBeInViewport()
      const body = panel(page).getByTestId('chunk-context-body')
      const actions = page.getByTestId('annotation-review')
      const top = (await actions.boundingBox())?.y
      // The passage is scrolled to Brně within itself; the sidebar does not scroll.
      expect(await body.evaluate(el => el.scrollTop), `${width}: the passage scrolled`).toBeGreaterThan(0)
      expect(await panel(page).evaluate(el => el.closest('.scroll')?.scrollTop ?? 0), `${width}: the sidebar did not`).toBe(0)
      // Scrolling the passage by hand moves only the passage. Measured by where the annotation
      // is on the screen, not by scrollTop: scrolling up near the start loads earlier text
      // (#780), and keeping the reading position then raises scrollTop while the text stays.
      const before = (await mark(page).boundingBox())!.y
      await body.hover()
      await page.mouse.wheel(0, -600)
      await expect.poll(async () => (await mark(page).boundingBox())?.y ?? before,
        `${width}: the passage scrolls by the wheel`).toBeGreaterThan(before)
      expect((await actions.boundingBox())?.y, `${width}: the actions stay in place`).toBe(top)
      await expect(actions.getByRole('button', { name: 'Confirm' })).toBeInViewport()
      // Scrolled away from the annotation, the passage offers the way back to it.
      const back = panel(page).getByTestId('chunk-context-back').filter({ visible: true })
      await body.evaluate(el => { el.scrollTop = 0 })
      await expect(back).toHaveText('arrow_downwardBack to annotation')
      await back.click()
      await expect(mark(page)).toBeInViewport()
      await expect(back).toHaveCount(0)
    }
  })

  test('scrolling near the start loads earlier text once, keeping the reading position (#780)', async ({ page }) => {
    const reads = await longDocument(page, { length: 40, placed: { [novak]: 2, [brno]: 20 } })
    await useViewport(page, 'wide')
    await openWorkspace(page)
    await row(page, 'Brně').click()
    await expect(mark(page)).toHaveText('Brně')
    const body = panel(page).getByTestId('chunk-context-body')
    const sections = panel(page).locator('.chunk-context__chunk')
    const count = await sections.count()
    // Near the start without the user scrolling: nothing is loaded.
    await body.evaluate(el => { el.scrollTop = 120 })
    await page.waitForTimeout(300)
    expect(reads.adjacent).toBe(0)

    // The paragraph at the top of the view, and where it is in the view.
    const first = await sections.first().getAttribute('data-chunk-id')
    const topOf = (id: string) => body.evaluate((el, id) =>
      el.querySelector(`[data-chunk-id="${id}"]`)!.getBoundingClientRect().top - el.getBoundingClientRect().top, id)
    const before = await topOf(first!)
    await body.hover()
    await page.mouse.wheel(0, -40)
    await expect(sections).toHaveCount(count + 5)
    await expect(sections.first()).not.toHaveAttribute('data-chunk-id', first!)
    // The text above was added without moving what is read: only the wheel's own step.
    await expect.poll(() => topOf(first!)).toBeGreaterThan(before)
    expect(await topOf(first!) - before, 'no jump by the added paragraphs').toBeLessThan(120)
    // One gesture, one read: finishing the load asks for nothing more.
    await page.waitForTimeout(500)
    expect(reads.adjacent).toBe(1)
  })

  test('closing the sidebar on a phone returns to the open row (#669)', async ({ page }) => {
    await longDocument(page, { length: 40, placed: { [novak]: 2, [brno]: 30 } })
    await useViewport(page, 'phone')
    await openWorkspace(page)
    await row(page, 'Brně').click()
    await expect(mark(page)).toHaveText('Brně')
    await page.getByRole('button', { name: 'Close sidebar' }).click()
    await expect(row(page, 'Brně')).toBeFocused()
    await expect(row(page, 'Brně')).toBeInViewport()
  })

  test('with reduced motion the passage moves at once', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await longDocument(page, { length: 40, placed: { [novak]: 2, [brno]: 20 } })
    await useViewport(page, 'wide')
    await openWorkspace(page)
    await row(page, 'Jan Novák').click()
    await expect(mark(page)).toHaveText('Jan Novák')
    for (let i = 0; i < 4; i++) {
      await panel(page).getByRole('button', { name: 'Show later text' }).click()
      await expect(panel(page).getByRole('button', { name: 'Show later text' })).toBeEnabled()
    }
    await mark(page).evaluate(el => el.scrollIntoView({ block: 'center' }))

    const trace = await recordScroll(panel(page))
    await row(page, 'Brně').click()
    await expect(mark(page)).toHaveText('Brně')
    const path = await trace.stop()
    // No animation: the move to Brně is a single step that ends the motion. The full suite
    // has shown a ~20 px shift just before it (likely scroll anchoring while the header's
    // annotation details change height); such small shifts are not animation.
    const screen = await (await recordScroll(panel(page))).height()
    const steps = path.slice(1).map((top, i) => top - path[i])
    const moves = steps.flatMap((step, i) => Math.abs(step) > screen / 2 ? [i] : [])
    expect(moves, `one step: ${path.join(' ')}`).toEqual([steps.length - 1])
    expect(steps.slice(0, -1).every(step => Math.abs(step) < 50), `no animation: ${path.join(' ')}`).toBe(true)
    await expect(mark(page)).toBeInViewport()
  })
})

test('Next brings the open row into view and keeps focus on the sidebar (#704)', async ({ page }) => {
  // Without smooth scrolling, so that each scroll is complete when it is measured.
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await useViewport(page, 'wide')
  await openWorkspace(page)
  await rows(page).first().click()
  await expect(rows(page).first()).toHaveAttribute('aria-current', 'true')
  // The sidebar slides in and narrows the page, which can wrap the toolbar: measure the rows
  // only once it is fully in and the page ends where it starts.
  await expect.poll(() => page.evaluate(() => {
    const drawer = document.querySelector('.q-drawer--right')?.getBoundingClientRect()
    const workspace = document.querySelector('[data-testid=collection-annotations]')?.getBoundingClientRect()
    if (!drawer || !workspace) return false
    return Math.round(drawer.right) <= window.innerWidth && Math.round(workspace.right) <= Math.round(drawer.left)
  })).toBe(true)
  // Shorten the window so that the first two rows fit, with room for the rows' scroll margin,
  // and the later ones do not.
  const second = await rows(page).nth(1).boundingBox()
  await page.setViewportSize({ width: viewports.wide.width, height: Math.ceil(second!.y + second!.height + 12) })
  await expect(rows(page).nth(2)).not.toBeInViewport({ ratio: 1 })

  const next = page.getByTestId('row-next')
  // A mouse press leaves focus in the button (Quasar's focus helper inside it), a key press on
  // the button itself; either way Enter presses it again.
  const focusInNext = () => next.evaluate(el => el.contains(document.activeElement))
  const scrollY = () => page.evaluate(() => window.scrollY)
  const before = await scrollY()
  await next.click()
  await expect(rows(page).nth(1)).toHaveAttribute('aria-current', 'true')
  // A visible row does not move the list.
  expect(await scrollY()).toBe(before)
  expect(await focusInNext()).toBe(true)

  await page.keyboard.press('Enter')
  await expect(rows(page).nth(2)).toHaveAttribute('aria-current', 'true')
  await expect(rows(page).nth(2)).toBeInViewport({ ratio: 1 })
  await expect(next).toBeFocused()

  // A row hidden under the fixed app header is brought out below it, not just to the
  // viewport's top edge. Room below the list lets the page scroll the next row under the header.
  await page.evaluate(() => { document.body.style.paddingBottom = '2000px' })
  const header = (await page.locator('.q-header').boundingBox())!
  const headerBottom = header.y + header.height
  const fourth = rows(page).nth(3)
  await fourth.evaluate((el, bottom) => {
    window.scrollBy(0, el.getBoundingClientRect().top - bottom / 2)
  }, headerBottom)
  expect((await fourth.boundingBox())!.y).toBeLessThan(headerBottom)
  await page.keyboard.press('Enter')
  await expect(fourth).toHaveAttribute('aria-current', 'true')
  // (The last row: Next is disabled now, so it cannot keep focus.)
  await expect.poll(async () => (await fourth.boundingBox())!.y).toBeGreaterThanOrEqual(headerBottom)
})

test('a review queue: reviewed rows stay in place, shortcuts decide and move, the position is announced (#690)', async ({ page, request }) => {
  const proposals = [fixture.span('lhota_automatic'), fixture.span('praha_automatic')]
  await useViewport(page, 'wide')
  await openWorkspace(page, 'annotator')
  const context = page.getByTestId('annotation-context')
  const announcement = page.getByTestId('annotation-announcement')
  try {
    await page.getByTestId('concordance-status-pos').click() // proposals only
    await expect(rows(page)).toHaveCount(2)
    const [first, second] = [rows(page).nth(0), rows(page).nth(1)]
    const secondText = (await second.locator('.kwic__key-label').textContent()) ?? ''
    await first.click()
    await expect(context.getByTestId('annotation-position')).toHaveText('1 / 2')
    // A proposal has neither state pressed; both name the action they take.
    await expect(page.getByTestId('row-approve')).toHaveAttribute('aria-pressed', 'false')
    await expect(page.getByTestId('row-reject')).toHaveAttribute('aria-pressed', 'false')
    await expect(page.getByTestId('annotation-review').getByRole('button')).toHaveText(['checkConfirm', 'blockReject'])
    await expect(page.getByTestId('row-prev')).toBeDisabled()

    // Shortcuts act on the sidebar while it has focus; not while focus is in the list.
    await page.getByTestId('row-next').focus()
    await page.keyboard.press('Alt+C')
    await expect(second).toHaveAttribute('aria-current', 'true')
    await expect(announcement).toContainText(`Confirmed. 2 / 2: ${secondText.trim().slice(0, 20)}`)
    await expect(announcement).toContainText('Last annotation.')
    // The confirmed row stays in place, at its new state, marked as out of the filters.
    await expect(rows(page)).toHaveCount(2)
    await expect(first).toContainText('Confirmed')
    await expect(first).toHaveClass(/kwic__row--unmatched/)
    await expect(page.getByTestId('concordance-unmatched')).toContainText('1 reviewed row no longer matches the filters')
    await expect(page.getByTestId('row-next')).toBeDisabled()

    // Back to it: Confirmed is pressed now; choosing it again writes nothing.
    await page.getByTestId('row-reject').focus()
    await page.keyboard.press('Alt+ArrowUp')
    await expect(first).toHaveAttribute('aria-current', 'true')
    await expect(page.getByTestId('row-approve')).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByTestId('annotation-review').getByRole('button')).toHaveText(['checkConfirmed', 'blockReject'])
    await expect(page.getByTestId('row-reject')).toBeFocused()
    let reviews = 0
    page.on('request', r => { if (r.url().endsWith('/annotations/review')) reviews++ })
    await page.keyboard.press('Alt+C')
    await expect(second).toHaveAttribute('aria-current', 'true')
    await expect(announcement).toContainText('Already confirmed. 2 / 2')
    expect(reviews).toBe(0)

    // Rejecting the second keeps both rows; the list changes when it is read again.
    await page.keyboard.press('Alt+R')
    await expect(second).toContainText('Rejected')
    await expect(announcement).toContainText('Rejected.')
    // The last row stays open: Rejected is pressed and named as the state, Confirm as the action.
    await expect(second).toHaveAttribute('aria-current', 'true')
    await expect(page.getByTestId('row-reject')).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByTestId('row-approve')).toHaveAttribute('aria-pressed', 'false')
    await expect(page.getByTestId('annotation-review').getByRole('button')).toHaveText(['checkConfirm', 'blockRejected'])
    await expect(page.getByTestId('concordance-unmatched')).toContainText('2 reviewed rows no longer match the filters')
    await page.getByTestId('concordance-refresh').click()
    await expect(page.getByTestId('concordance-empty')).toBeVisible()
  } finally {
    for (const span of proposals) await patchSpan(request, span.id, { type: 'auto' })
  }
})

test('inline row review: a status switch of one shape in every row, nothing moves, grid shortcuts move focus (#690 phase B)', async ({ page }) => {
  const proposals = [fixture.span('lhota_automatic'), fixture.span('praha_automatic')]
  await useViewport(page, 'wide')
  await openWorkspace(page, 'annotator')
  const announcement = page.getByTestId('annotation-announcement')
  const width = (locator: Locator) => locator.evaluate(e => e.getBoundingClientRect().width)
  try {
    await page.getByTestId('concordance-status-pos').click() // proposals only
    await expect(rows(page)).toHaveCount(2)
    const [first, second] = [rows(page).nth(0), rows(page).nth(1)]
    const cell = first.getByTestId('kwic-review')
    const idle = await width(cell)
    const box = () => first.locator('.kwic__switch').boundingBox()
    const place = await box()
    // The status is a switch, named in words; a proposal has neither half pressed.
    await expect(first.getByTestId('kwic-status')).toContainText('Proposal')
    await expect(first.getByTestId('kwic-approve')).toBeVisible()
    await expect(first.getByTestId('kwic-approve')).toHaveAttribute('aria-pressed', 'false')
    await expect(first.getByTestId('kwic-reject')).toHaveAttribute('aria-pressed', 'false')
    await first.hover()
    expect(await width(cell), 'no width change on hover').toBe(idle)
    expect(await box(), 'the switch does not move on hover').toEqual(place)

    // A button decides its row only: it neither opens nor checks the row, nor takes focus.
    let reviews = 0
    page.on('request', r => { if (r.url().endsWith('/annotations/review')) reviews++ })
    await first.getByTestId('kwic-approve').click()
    await expect(first.getByTestId('kwic-approve')).toHaveAttribute('aria-pressed', 'true')
    await expect(first.getByTestId('kwic-status')).toContainText('Confirmed')
    await expect(first.getByTestId('kwic-reject')).toHaveAttribute('aria-pressed', 'false')
    // The same switch in the same place, whatever the state.
    await page.mouse.move(0, 0)
    expect(await box(), 'the switch does not move with the state').toEqual(place)
    expect(reviews).toBe(1)
    expect(await width(cell), 'no width change after saving').toBe(idle)
    await expect(first).not.toHaveAttribute('aria-current', 'true')
    await expect(first).toHaveAttribute('aria-selected', 'false')
    await expect(page.getByTestId('annotation-context')).toBeHidden()
    // It stays in place, out of the filters now.
    await expect(first).toHaveClass(/kwic__row--unmatched/)
    await expect(announcement).toContainText('Confirmed. 1 / 2')
    await expect(page.getByTestId('review-report')).toHaveCount(0)
    await expect(page.getByTestId('undo-bar')).toHaveCount(0)

    // Keyboard: Alt+R rejects the focused row; it stays focused on the last row of the page.
    await first.focus()
    await page.keyboard.press('ArrowDown')
    await expect(second).toBeFocused()
    await page.keyboard.press('Alt+R')
    await expect(second.getByTestId('kwic-status')).toContainText('Rejected')
    await expect(announcement).toContainText('Rejected. 2 / 2')
    await expect(announcement).toContainText('Last annotation.')
    await expect(second).toBeFocused()
    // Choosing the state in effect writes nothing; Alt+↑ opens the previous row and focuses it.
    await page.keyboard.press('Alt+R')
    await expect(announcement).toContainText('Already rejected.')
    expect(reviews).toBe(2)
    await page.keyboard.press('Alt+ArrowUp')
    await expect(first).toBeFocused()
    await expect(first).toHaveAttribute('aria-current', 'true')
    await expect(page.getByTestId('annotation-position')).toHaveText('1 / 2')
    // Alt+C on the focused (already confirmed) row moves focus on; the sidebar stays.
    await page.keyboard.press('Alt+C')
    await expect(second).toBeFocused()
    await expect(first).toHaveAttribute('aria-current', 'true')
    expect(reviews).toBe(2)
  } finally {
    for (const span of proposals) await patchSpan(page.request, span.id, { type: 'auto' })
  }
})

test('filters, selection and the open row survive a visit to the document', async ({ page }) => {
  await useViewport(page, 'narrow')
  await openWorkspace(page)
  await page.getByLabel('Contains words', { exact: true }).fill('nová')
  await expect(rows(page)).toHaveCount(1)
  await row(page, 'Jan Novák').getByRole('checkbox').click()
  await row(page, 'Jan Novák').click()

  await panel(page).getByTestId('chunk-context-title').click()
  await expect(page.locator('.doc-header').getByTestId('document-title')).toBeVisible()
  await expect(page.locator('.text-segment.is-tagged', { hasText: 'Jan Novák' }).first()).toBeVisible()

  await page.getByRole('link', { name: 'Back to annotations' }).click()
  await expect(page.getByLabel('Contains words', { exact: true })).toHaveValue('nová')
  await expect(rows(page)).toHaveCount(1)
  await expect(page.getByTestId('concordance-selected')).toHaveText('1 selected')
  await expect(row(page, 'Jan Novák')).toHaveAttribute('aria-current', 'true')
})

test('the text scope, document filters and filter chips compose (#663)', async ({ page }) => {
  await useViewport(page, 'narrow')
  await openWorkspace(page)
  const all = await rows(page).count()

  // "hejtman" occurs only in the context of the chronicle's annotations, never in an annotation.
  await page.getByLabel('Contains words', { exact: true }).fill('hejtman')
  await expect(page.getByText('No annotations match these filters.')).toBeVisible()
  await page.getByTestId('concordance-text-scope').click()
  await page.getByRole('option', { name: 'Context' }).click()
  await expect(row(page, 'Jan Novák')).toBeVisible()
  await expect(row(page, 'Jan Novák').locator('.kwic__left mark.kwic__match')).toHaveText('hejtman')
  await expect(row(page, 'Jan Novák').locator('.kwic__key mark')).toHaveCount(0)
  const chips = page.getByTestId('concordance-chips')
  await expect(chips).toContainText('Contains words in context:hejtman')

  // A document filter of the shared criteria: only the letters' title matches.
  await page.getByLabel('Contains words', { exact: true }).clear()
  await expect(rows(page)).toHaveCount(all)
  await page.getByTestId('concordance-more-filters').click()
  await expect(page.getByTestId('concordance-more-filters')).toHaveAttribute('aria-expanded', 'true')
  await page.getByLabel('Title contains').fill('dopisy')
  await page.getByLabel('Title contains').press('Enter')
  await expect(chips).toContainText('Title contains:dopisy')
  await expect(page.getByTestId('concordance-more-filters')).toContainText('More filters (1)')
  await expect.poll(() => rows(page).count()).toBeLessThan(all)
  await expect(rows(page).first()).toBeVisible()
  for (const source of await rows(page).locator('.kwic__title').allTextContents()) expect(source).toBe('Dopisy z Prahy')

  await page.getByRole('button', { name: 'Remove filter Title contains: dopisy' }).click()
  await expect(rows(page)).toHaveCount(all)
  await expect(chips).toHaveCount(0)
})

test('on a phone the filter form is closed behind a summary and keeps what was entered (#660 review)', async ({ page }) => {
  await useViewport(page, 'phone')
  await openWorkspace(page)
  const toggle = page.getByTestId('concordance-filters-toggle')
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await expect(page.getByTestId('concordance-text')).toBeHidden()
  await expect(rows(page).first()).toBeVisible()
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-expanded', 'true')
  await page.getByLabel('Contains words', { exact: true }).fill('nová')
  await expect(page.getByTestId('concordance-chips')).toContainText('nová')
  await toggle.click()
  await expect(page.getByTestId('concordance-text')).toBeHidden()
  await expect(page.getByTestId('concordance-summary')).toContainText('nová')
  await toggle.click()
  await expect(page.getByLabel('Contains words', { exact: true })).toHaveValue('nová')
})

test('column headers sort the whole result both ways and bring up their filters, with the sidebar open (#665)', async ({ page }) => {
  await useViewport(page, 'narrow')
  await openWorkspace(page)
  const keys = () => rows(page).locator('.kwic__key-label').allTextContents()
  const annotation = page.getByTestId('kwic-head-annotation')

  await page.getByTestId('kwic-sort-year').click()
  await expect(page.getByTestId('kwic-head-year')).toHaveAttribute('aria-sort', 'ascending')
  await expect(annotation).toHaveAttribute('aria-sort', 'none')
  await expect.poll(() => rows(page).locator('.kwic__year').allInnerTexts()).toEqual(['1851', '1851', '1851', '1902'])
  // The left context sorts by its nearest word, in Czech dictionary order (#666).
  await page.getByTestId('kwic-sort-left').click()
  await expect(page.getByTestId('kwic-head-left')).toHaveAttribute('aria-sort', 'ascending')
  await expect(page.getByTestId('kwic-head-year')).toHaveAttribute('aria-sort', 'none')
  const nearest = async () => (await rows(page).locator('.kwic__left').allTextContents())
    .map(t => t.match(/[\p{L}\p{M}\p{N}]+/gu)?.at(-1) ?? '')
  await expect.poll(async () => {
    const words = await nearest()
    return words.length > 1 && words.join('|') === [...words].sort((a, b) => a.localeCompare(b, 'cs')).join('|')
  }).toBe(true)

  // With the sidebar open (the list narrows; source and year give way, the toolbar sorts by
  // them), by keyboard: the annotation header sorts ascending, then descending, the whole result.
  await row(page, 'Lhoty').click()
  await expect(panel(page).getByTestId('annotation-context')).toBeVisible()
  await expect(page.getByTestId('kwic-sort-year')).toBeHidden()
  await page.getByTestId('kwic-sort-annotation').focus()
  await page.keyboard.press('Enter')
  await expect(annotation).toHaveAttribute('aria-sort', 'ascending')
  await expect.poll(keys).toEqual(['Brně', 'Jan Novák', 'Lhoty', 'Prahy'])
  await page.keyboard.press('Enter')
  await expect(annotation).toHaveAttribute('aria-sort', 'descending')
  await expect.poll(keys).toEqual(['Prahy', 'Lhoty', 'Jan Novák', 'Brně'])
  // Sorting kept the open row and the sidebar.
  await expect(row(page, 'Lhoty')).toHaveAttribute('aria-current', 'true')
  await expect(panel(page).getByTestId('annotation-context')).toBeVisible()

  // A context header's filter searches the context; it opens no row and checks none.
  await page.getByTestId('kwic-filter-right').click()
  await expect(page.getByTestId('concordance-text-scope')).toContainText('Context')
  await expect(page.getByLabel('Contains words', { exact: true })).toBeFocused()
  await page.keyboard.type('hejtman')
  // Only in the chronicle: the letter's annotation goes.
  await expect(row(page, 'Prahy')).toHaveCount(0)
  await expect(row(page, 'Jan Novák').locator('.kwic__left mark.kwic__match')).toHaveText('hejtman')
  await expect(page.getByTestId('kwic-filter-left')).toHaveAccessibleName('Filter by words in the context (active)')
  await expect(page.getByTestId('concordance-selected')).toHaveCount(0)
  await page.getByRole('button', { name: 'Remove filter Contains words in context: hejtman' }).click()
  await expect(rows(page)).toHaveCount(4)

  // From *Both*, each text header's filter selects exactly its own field, as it says (#665 review).
  await page.getByTestId('concordance-text-scope').click()
  await page.getByRole('option', { name: 'Both' }).click()
  await expect(page.getByTestId('concordance-text-scope')).toContainText('Both')
  await page.getByTestId('kwic-filter-annotation').click()
  await expect(page.getByTestId('concordance-text-scope')).toContainText('Annotation')
  await expect(page.getByLabel('Contains words', { exact: true })).toBeFocused()
  await page.getByTestId('concordance-text-scope').click()
  await page.getByRole('option', { name: 'Both' }).click()
  await page.getByTestId('kwic-filter-left').click()
  await expect(page.getByTestId('concordance-text-scope')).toContainText('Context')
})

test('in-cell value filters compose as chips and never open, check or unselect rows (#665)', async ({ page }) => {
  await useViewport(page, 'wide')
  await openWorkspace(page)
  const chips = page.getByTestId('concordance-chips')
  const menu = page.getByTestId('kwic-row-menu')
  const chronicle = fixture.document('chronicle').properties.title as string
  const checked = page.getByTestId('concordance-selected')

  // Right click on a displayed source: Only this source. No row opens or is checked.
  await row(page, 'Jan Novák').locator('.kwic__source').click({ button: 'right' })
  await expect(menu.getByTestId('kwic-refine-group-source')).toContainText(`Source · ${chronicle}`)
  await menu.getByTestId('kwic-refine-source-only').click()
  await expect(chips).toContainText(`Source:${chronicle}`)
  await expect(row(page, 'Prahy')).toHaveCount(0)
  for (const source of await rows(page).locator('.kwic__title').allTextContents()) expect(source).toBe(chronicle)
  await expect(panel(page)).toHaveCount(0)
  await expect(checked).toHaveCount(0)
  await expect(menu, 'the menu closed').toHaveCount(0)

  // By keyboard (Shift+F10 on the focused row): exclude the proposals' status; it composes.
  await row(page, 'Lhoty').focus()
  await page.keyboard.press('Shift+F10')
  await expect(menu.getByTestId('kwic-refine-group-status')).toContainText('Status · Proposal')
  await menu.getByTestId('kwic-refine-status-exclude').click()
  await expect(row(page, 'Lhoty')).toHaveCount(0)
  await expect(chips).toContainText('Status:Confirmed')
  await expect(chips).toContainText(`Source:${chronicle}`)

  // Removing a chip undoes its filter.
  await page.getByRole('button', { name: 'Remove filter Status: Confirmed' }).click()
  await expect(row(page, 'Lhoty')).toBeVisible()
  await expect(row(page, 'Prahy')).toHaveCount(0)
  await page.getByRole('button', { name: `Remove filter Source: ${chronicle}` }).click()
  await expect(rows(page)).toHaveCount(4)

  // With the sidebar open (narrow), the row's menu button: Only this year.
  await useViewport(page, 'narrow')
  await row(page, 'Jan Novák').click()
  await expect(panel(page).getByTestId('annotation-context')).toBeVisible()
  await rows(page).filter({ hasText: 'Prahy' }).hover()
  await row(page, 'Prahy').getByTestId('kwic-row-more').click()
  await menu.getByTestId('kwic-refine-year-only').click()
  await expect(chips).toContainText('Years:1902')
  await expect(row(page, 'Jan Novák')).toHaveCount(0)
  await page.getByRole('button', { name: 'Remove filter Years: 1902' }).click()
  await expect(rows(page)).toHaveCount(4)
  // The open row stayed open.
  await expect(row(page, 'Jan Novák')).toHaveAttribute('aria-current', 'true')

  // Selecting a word with the mouse opens no row; right click on it filters by it, in the field
  // it was selected in, with the matching rules said.
  const right = row(page, 'Lhoty').locator('.kwic__right')
  const box = (await right.boundingBox())!
  const word = await right.evaluate(el => {
    const text = el.textContent ?? ''
    const match = /[\p{L}]{4,}/u.exec(text)!
    const node = Array.from(el.childNodes).find(n => n.textContent?.includes(match[0]))!
    const range = document.createRange()
    const at = node.textContent!.indexOf(match[0])
    range.setStart(node, at)
    range.setEnd(node, at + match[0].length)
    const r = range.getBoundingClientRect()
    return { text: match[0], x: r.left, y: r.top + r.height / 2, width: r.width }
  })
  expect(word.x).toBeGreaterThanOrEqual(box.x)
  await page.mouse.move(word.x + 1, word.y)
  await page.mouse.down()
  await page.mouse.move(word.x + word.width - 1, word.y, { steps: 5 })
  await page.mouse.up()
  expect((await page.evaluate(() => getSelection()!.toString())).length).toBeGreaterThan(0)
  await expect(row(page, 'Jan Novák')).toHaveAttribute('aria-current', 'true')
  await page.mouse.click(word.x + word.width / 2, word.y, { button: 'right' })
  const words = menu.getByTestId('kwic-refine-group-words')
  await expect(words).toContainText('Shows only annotations with every word you type in the left or right context')
  await menu.getByTestId('kwic-refine-words').click()
  await expect(chips).toContainText('Contains words in context:')
  await expect(page.getByTestId('concordance-text-scope')).toContainText('Context')
  await expect(row(page, 'Lhoty').locator('.kwic__right mark.kwic__match').first()).toBeVisible()
  await expect(checked).toHaveCount(0)
})

test('find similar from the sidebar, ranked by meaning, as a top k (#664)', async ({ page }) => {
  await useViewport(page, 'wide')
  await openWorkspace(page)
  const range = page.getByTestId('concordance-range')
  const ranked = page.getByTestId('concordance-ranked')

  // From the open annotation: the others, ranked, without it; its chip names and opens it.
  await row(page, 'Jan Novák').click()
  await page.getByTestId('row-find-similar').click()
  await expect(range).toHaveText('Rows 1–3 of 3 ranked annotations')
  await expect(ranked).toHaveText('Top 100 most similar (3 found)')
  await expect(row(page, 'Jan Novák')).toHaveCount(0)
  await expect(rows(page).getByTestId('kwic-rank')).toHaveText(['#1', '#2', '#3'])
  await expect(page.getByTestId('select-all-matches')).toHaveText('Select these top 3')
  const chip = page.getByTestId('concordance-chip-similar')
  await expect(chip).toContainText('Similar to:\'Jan Novák\'')

  // The source stays pinned above the results, named and reachable, while it is not ranked.
  const pinned = page.getByTestId('similar-source')
  await expect(pinned).toContainText("'Jan Novák'")
  await expect(pinned.getByTestId('similar-source-status')).toContainText('not one of the ranked matches')

  await pinned.getByTestId('similar-source-include').click()
  await expect(range).toHaveText('Rows 1–4 of 4 ranked annotations')
  await expect(rows(page).first()).toContainText('Jan Novák') // nearest to itself

  await chip.locator('.filter-chips__value').click()
  await expect(page.getByTestId('annotation-context-text')).toHaveText('Jan Novák')

  // Back to the previous view: the query from before Find similar, not a reconstruction.
  await pinned.getByTestId('similar-source-back').click()
  await expect(range).toHaveText('Rows 1–4 of 4 matching annotations')
  await expect(pinned).toHaveCount(0)
  await row(page, 'Jan Novák').click()
  await page.getByTestId('row-find-similar').click()
  await expect(pinned).toBeVisible()

  // Removing the chip leaves the mode; every match again, sortable.
  await page.getByRole('button', { name: 'Stop finding annotations similar to \'Jan Novák\'' }).click()
  await expect(range).toHaveText('Rows 1–4 of 4 matching annotations')
  await expect(ranked).toHaveCount(0)

  // Similarity text: a ranked top k of the filters (no mode selector, no top-k control).
  await expect(page.getByTestId('concordance-mode')).toHaveCount(0)
  await page.getByLabel('Similar meaning', { exact: true }).fill('hejtman')
  await expect(range).toHaveText('Rows 1–4 of 4 ranked annotations')
  await expect(ranked).toContainText('Top 100 by meaning')
  await expect(page.getByTestId('concordance-chips')).toContainText('Similar meaning:hejtman')
  await page.getByTestId('concordance-status-pos').click() // proposals only: filters apply before ranking
  await expect(range).toHaveText('Rows 1–2 of 2 ranked annotations')
})

test('a long cross-chunk annotation is cut in its middle in its row and complete in the sidebar', async ({ page, request }) => {
  const first = fixture.chunk('chronicle_1').text
  const second = fixture.chunk('chronicle_2').text
  await createSpan(request, 'chronicle_1', 10, first.length + 30)
  await useViewport(page, 'narrow')
  await openWorkspace(page)
  const long = row(page, first.slice(10, 40))
  const key = long.locator('.kwic__key')
  await expect(long.locator('.kwic__key-label')).toHaveText(first.slice(10) + second.slice(0, 30))

  // One line, centered, the contexts touching it; cut in the middle (#665): its first half shows
  // the start, its second half the end, so both contexts read on into it.
  const cut = async () => {
    const [box, line] = await Promise.all([key.boundingBox(), row(page, 'Brně').locator('.kwic__key').boundingBox()])
    expect(Math.abs(box!.height - line!.height), 'one line').toBeLessThanOrEqual(1)
    const parts = await long.getByTestId('kwic-text').evaluate(el => {
      const text = el.getBoundingClientRect()
      const [left, k, right] = ['.kwic__left', '.kwic__key', '.kwic__right'].map(s => el.querySelector(s)!.getBoundingClientRect())
      const head = el.querySelector<HTMLElement>('.kwic__key-head')!
      const tail = el.querySelector<HTMLElement>('.kwic__key-tail')!
      const tailText = tail.firstElementChild!.getBoundingClientRect()
      return {
        gapBefore: k.left - left.right,
        gapAfter: right.left - k.right,
        off: (k.left + k.right) / 2 - (text.left + text.right) / 2,
        headCut: head.scrollWidth > head.clientWidth,
        headStart: head.firstElementChild!.getBoundingClientRect().left - head.getBoundingClientRect().left,
        tailCut: tail.scrollWidth > tail.clientWidth,
        tailEnd: tail.getBoundingClientRect().right - tailText.right
      }
    })
    expect(Math.abs(parts.gapBefore)).toBeLessThanOrEqual(0.5)
    expect(Math.abs(parts.gapAfter)).toBeLessThanOrEqual(0.5)
    expect(Math.abs(parts.off)).toBeLessThanOrEqual(1.5)
    expect([parts.headCut, parts.tailCut], 'both halves cut').toEqual([true, true])
    expect(Math.abs(parts.headStart), 'the start shown').toBeLessThanOrEqual(0.5)
    expect(Math.abs(parts.tailEnd), 'the end shown').toBeLessThanOrEqual(0.5)
  }
  await cut()
  // A short one is not cut, though its halves differ in width.
  expect(await row(page, 'Prahy').locator('.kwic__key-head, .kwic__key-tail')
    .evaluateAll(els => els.map(e => e.scrollWidth <= e.clientWidth))).toEqual([true, true])
  await useViewport(page, 'phone')
  await expect.poll(async () => { try { await cut(); return true } catch { return false } }).toBe(true)
  await useViewport(page, 'narrow')

  await long.click()
  const marks = panel(page).getByTestId('chunk-context-mark')
  await expect(marks).toHaveText([first.slice(10), second.slice(0, 30)])
  await expect(panel(page).getByTestId('annotation-context-text')).toHaveText(first.slice(10) + second.slice(0, 30))
})

test('copying from a row gives the source text unchanged, also of a cut annotation (#665 review)', async ({ page, request }) => {
  const first = fixture.chunk('chronicle_1').text
  const second = fixture.chunk('chronicle_2').text
  await createSpan(request, 'chronicle_1', 10, first.length + 30)
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await useViewport(page, 'narrow')
  await openWorkspace(page)
  const long = row(page, first.slice(10, 40))
  await expect(long.locator('.kwic__key-head')).toBeVisible()
  expect(await long.locator('.kwic__key-head').evaluate(e => e.scrollWidth > e.clientWidth), 'the long one is cut').toBe(true)

  /** Selects from `start` characters into the first text of `from` to `end` into the last of `to`
   * (both within the row), copies with the keyboard and returns the clipboard text. */
  async function copy (text: Locator, from: string, start: number, to: string, end: number | 'end') {
    await text.evaluate((el, [from, start, to, end]) => {
      const texts = (s: string) => {
        const walker = document.createTreeWalker(el.querySelector(s)!, NodeFilter.SHOW_TEXT)
        const nodes: Text[] = []
        while (walker.nextNode()) if ((walker.currentNode as Text).length) nodes.push(walker.currentNode as Text)
        return nodes
      }
      const last = texts(to as string).at(-1)!
      const range = document.createRange()
      range.setStart(texts(from as string)[0], start as number)
      range.setEnd(last, end === 'end' ? last.length : end as number)
      const selection = getSelection()!
      selection.removeAllRanges()
      selection.addRange(range)
    }, [from, start, to, end] as const)
    await page.keyboard.press('ControlOrMeta+c')
    return await page.evaluate(() => navigator.clipboard.readText())
  }

  // A short annotation alone, then with the words around it.
  const novak = rows(page).filter({ has: page.locator('.kwic__key-label', { hasText: /^Jan Novák$/ }) }).first().getByTestId('kwic-text')
  expect(await copy(novak, '.kwic__key', 0, '.kwic__key', 'end')).toBe('Jan Novák')
  const left = (await novak.locator('.kwic__left').textContent())!
  const at = first.indexOf('hejtman Jan Novák')
  expect(await copy(novak, '.kwic__left', left.length - 'hejtman '.length, '.kwic__right', ' a ubytoval'.length))
    .toBe(first.slice(at, at + 'hejtman Jan Novák a ubytoval'.length))
  // The cut annotation whole, though only its start and end are shown.
  expect(await copy(long.getByTestId('kwic-text'), '.kwic__key', 0, '.kwic__key', 'end')).toBe(first.slice(10) + second.slice(0, 30))
})

test('narrow lists keep the tag and status and give up source and year first (#665 review)', async ({ page }) => {
  const shown = (locator: Locator) => locator.evaluate(e => e.getBoundingClientRect().width > 8)
  const check = async (wide: boolean) => {
    const novak = row(page, 'Jan Novák')
    expect(await shown(novak.locator('.kwic__review')), 'status').toBe(true)
    expect(await shown(novak.locator('.kwic__tag')), 'tag').toBe(true)
    expect(await shown(novak.locator('.kwic__source')), 'source').toBe(wide)
    expect(await shown(novak.locator('.kwic__year')), 'year').toBe(wide)
    await expect(page.getByTestId('kwic-sort-year')).toBeVisible({ visible: wide })
    // Hidden only from view: the values stay in the row for assistive technology.
    await expect(novak.locator('.kwic__year')).toHaveText('1851')
  }
  await useViewport(page, 'wide')
  await openWorkspace(page)
  await check(true)
  // The sidebar narrows the list below 900 px.
  await useViewport(page, 'narrow')
  await row(page, 'Lhoty').click()
  await expect(panel(page).getByTestId('annotation-context')).toBeVisible()
  await check(false)
  await useViewport(page, 'phone')
  await openWorkspace(page)
  await check(false)
  // Without attribute columns the list fits: it does not scroll sideways.
  // (Polled: the layout settles after the viewport change closes the sidebar.)
  await expect.poll(() => page.getByTestId('kwic').evaluate(e => e.scrollWidth - e.clientWidth)).toBeLessThanOrEqual(0)
  const [list, status] = await Promise.all([page.getByTestId('kwic').boundingBox(), row(page, 'Jan Novák').locator('.kwic__review').boundingBox()])
  expect(status!.x + status!.width, 'status within the list').toBeLessThanOrEqual(list!.x + list!.width)
})

test('keyboard: Home shows the first row below the header, focus is drawn on checked rows, Escape closes the covering sidebar (#665 review)', async ({ page }) => {
  await useViewport(page, 'phone')
  await openWorkspace(page)
  const first = rows(page).first()
  // Home from the last row, the page scrolled so the first row is under the fixed app header (in
  // the viewport, so the browser alone would not scroll): it comes into view below the header.
  const header = (await page.locator('.q-header').boundingBox())!
  // Room below the list, as a full page of rows would leave.
  await page.getByTestId('collection-annotations').evaluate(el => { el.style.paddingBottom = '1500px' })
  await rows(page).last().evaluate(el => (el as HTMLElement).focus({ preventScroll: true }))
  await first.evaluate((el, bottom) => window.scrollBy(0, el.getBoundingClientRect().top - (bottom - 20)), header.y + header.height)
  expect((await first.boundingBox())!.y, 'the first row starts under the header').toBeLessThan(header.y + header.height)
  await page.keyboard.press('Home')
  await expect(first).toBeFocused()
  await expect.poll(async () => (await first.boundingBox())!.y).toBeGreaterThanOrEqual(header.y + header.height)

  // A checked row that has keyboard focus shows the focus ring across its text too.
  await first.getByRole('checkbox').click()
  await rows(page).nth(1).evaluate(el => (el as HTMLElement).focus())
  await page.keyboard.press('ArrowUp')
  await expect(first).toBeFocused()
  await expect(first).toHaveAttribute('aria-selected', 'true')
  await expect(first.getByTestId('kwic-text')).toHaveCSS('box-shadow', /inset/)

  // Enter opens the row in the sidebar, which covers the list on a phone; Escape closes it and
  // gives the keyboard back to the row.
  await page.keyboard.press('Enter')
  const drawer = page.locator('.q-drawer--right')
  await expect(panel(page).getByTestId('annotation-context')).toBeVisible()
  await expect(drawer).toBeInViewport()
  await page.keyboard.press('Escape')
  await expect(drawer).not.toBeInViewport()
  await expect(first).toBeFocused()

  // On a wide screen the sidebar sits beside the list and Escape leaves it open.
  await useViewport(page, 'wide')
  await first.click()
  await expect(panel(page).getByTestId('annotation-context')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(panel(page).getByTestId('annotation-context')).toBeVisible()
})

test('a long annotated text shows its first lines in the sidebar, the whole text on request', async ({ page, request }) => {
  const first = fixture.chunk('chronicle_1').text
  const second = fixture.chunk('chronicle_2').text
  await createSpan(request, 'chronicle_1', 0, first.length + second.length)
  await useViewport(page, 'phone')
  await openWorkspace(page)
  await row(page, first.slice(0, 30)).click()

  const text = panel(page).getByTestId('annotation-context-text')
  const toggle = panel(page).getByTestId('annotation-context-text-toggle')
  await expect(toggle).toHaveAttribute('aria-label', 'Show all text')
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  expect(await text.evaluate(e => e.scrollHeight > e.clientHeight), 'the text is clamped').toBe(true)
  const clamped = (await text.boundingBox())?.height ?? 0

  // The arrow unfolds it, smoothly; a click on the text folds it again.
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-label', 'Show less text')
  await expect.poll(async () => (await text.boundingBox())?.height ?? 0).toBeGreaterThan(clamped + 10)
  await text.click()
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await expect.poll(async () => (await text.boundingBox())?.height ?? 0).toBeLessThan(clamped + 2)

  // Another annotation opens clamped again; a short one has no toggle.
  await page.getByRole('button', { name: 'Close sidebar' }).click()
  await row(page, 'Prahy').click()
  await expect(text).toHaveText('Prahy')
  await expect(toggle).toHaveCount(0)
})

test('the tag and the position head the sidebar, the review is a choice of state; the tag chip changes the tag (#659, #690)', async ({ page, request }) => {
  const text = fixture.chunk('chronicle_2').text.slice(0, 8)
  await createSpan(request, 'chronicle_2', 0, 8)
  await useViewport(page, 'narrow')
  await openWorkspace(page)
  await row(page, text).click()
  const context = page.getByTestId('annotation-context')
  const review = page.getByTestId('annotation-review')
  const chip = page.getByTestId('row-retag')
  await expect(chip).toHaveAccessibleName(`Tag: ${fixture.tag('person').name}. Change tag`)
  // The tag and the place in the result first, then the decision, then the text.
  const y = async (locator: typeof chip) => (await locator.boundingBox())?.y ?? 0
  expect(await y(chip)).toBeLessThan(await y(review))
  expect(await y(review)).toBeLessThan(await y(context.getByTestId('annotation-context-text')))
  await expect(context.getByTestId('annotation-position')).toHaveText(/^\d+ \/ \d+$/)
  // Confirmed and Rejected are the states to choose; the one in effect is pressed, not disabled,
  // and named as the state, the other as the action. Delete is a quiet action of its own.
  await expect(review.getByRole('button')).toHaveText(['checkConfirmed', 'blockReject'])
  await expect(page.getByTestId('row-approve')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('row-approve')).toBeEnabled()
  await expect(page.getByTestId('row-reject')).toHaveAttribute('aria-pressed', 'false')
  await expect(page.getByTestId('row-reject')).toBeEnabled()
  await expect(page.getByTestId('row-approve')).toHaveAttribute('aria-keyshortcuts', 'Alt+C')
  // The tag's definition on the chip.
  await chip.hover()
  await expect(page.getByTestId('tag-chip-tooltip')).toContainText('Click to change the tag')
  await page.mouse.move(0, 0)
  await expect(review.getByRole('button', { name: 'Delete…' })).toHaveCount(0)
  await expect(context.getByTestId('annotation-secondary-actions').getByRole('button', { name: 'Delete…' })).toBeVisible()
  await expect(sidebarPanelButton(page, 'Annotation')).toHaveCount(1)
  // Origin is outside the height-capped attributes.
  await expect(context.getByTestId('annotation-context-details').getByTestId('annotation-provenance')).toHaveCount(0)
  await expect(context.getByTestId('annotation-provenance')).toBeVisible()

  await chip.click()
  const menu = page.getByRole('menu', { name: 'Change tag' })
  await expect(menu.getByRole('menuitem', { name: fixture.tag('person').name })).toHaveAttribute('aria-disabled', 'true')
  await menu.getByRole('menuitem', { name: fixture.tag('place').name }).click()
  await expect(chip).toHaveAccessibleName(`Tag: ${fixture.tag('place').name}. Change tag`)
  await expect(page.getByTestId('review-report')).toContainText('1 of 1')
})

test('a long document title takes two lines above the passage, the whole title in its tooltip (#659)', async ({ page }) => {
  const title = 'Karlínské listy : politickohospodářský neodvislý týdenník města Karlína, Holešovic, Libně a Vysočan. 2. 28'
  await page.route('**/api/documents/*/chunks/*/window*', async route => {
    const response = await route.fetch()
    const body = await response.json()
    body.document = { ...body.document, title }
    await route.fulfill({ response, json: body })
  })
  await useViewport(page, 'phone')
  await openWorkspace(page)
  await row(page, 'Jan Novák').click()
  const heading = panel(page).getByTestId('chunk-context-title')
  await expect(heading).toHaveAttribute('title', new RegExp('^' + title))
  const { lines, clipped } = await heading.evaluate(el => ({
    lines: Math.round(el.clientHeight / parseFloat(getComputedStyle(el).lineHeight)),
    clipped: el.scrollHeight > el.clientHeight
  }))
  expect(lines).toBe(2)
  expect(clipped, 'the title is longer than two lines here').toBe(true)
})

test('a shared user reads the same workspace', async ({ page }) => {
  await useViewport(page, 'phone')
  await openWorkspace(page, 'annotator')
  await expect(rows(page)).toHaveCount(4)
  await row(page, 'Prahy').click()
  await expect(panel(page).getByTestId('chunk-context-mark')).toHaveText('Prahy')
})

test('a review made in the document view shows in the workspace on return', async ({ page, request }) => {
  const lhota = fixture.span('lhota_automatic')
  const restore = (type: string) => patchSpan(request, lhota.id, { type })
  await useViewport(page, 'narrow')
  await openWorkspace(page)
  await row(page, 'Lhoty').click()
  await panel(page).getByTestId('chunk-context-title').click()
  await expect(page.locator('.doc-header').getByTestId('document-title')).toBeVisible()
  // The linked proposal is marked although AI Tagging (which shows proposals) is not open.
  await expect(page.locator('.text-segment.is-highlighted', { hasText: 'Lhoty' }).first()).toBeVisible()
  try {
    await restore('pos') // approved meanwhile (as from the document view's popover)
    await page.getByRole('link', { name: 'Back to annotations' }).click()
    await expect(row(page, 'Lhoty')).toContainText('Confirmed')
    await expect(row(page, 'Lhoty')).toHaveAttribute('data-annotation-id', lhota.id)
  } finally {
    await restore('auto')
  }
})

test('the open row follows edits made in the document view', async ({ page, request }) => {
  const novak = fixture.span('novak_manual')
  await useViewport(page, 'narrow')
  await openWorkspace(page)
  await row(page, 'Jan Novák').click()
  const openDocument = async () => {
    await panel(page).getByTestId('chunk-context-title').click()
    await expect(page.locator('.doc-header').getByTestId('document-title')).toBeVisible()
  }
  try {
    await openDocument()
    await patchSpan(request, novak.id, { start: 38 }) // "Jan Novák" -> "Novák"
    await page.getByRole('link', { name: 'Back to annotations' }).click()
    await expect(panel(page).getByTestId('annotation-context-text')).toHaveText('Novák')
    await expect(panel(page).getByTestId('chunk-context-mark')).toHaveText('Novák')

    await openDocument()
    await patchSpan(request, novak.id, { type: 'neg' }) // rejected: out of the default filters
    await page.getByRole('link', { name: 'Back to annotations' }).click()
    await expect(row(page, 'Novák')).toHaveCount(0)
    await expect(panel(page).getByTestId('annotation-context-gone')).toBeVisible()
    await expect(panel(page).getByTestId('chunk-context-mark')).toHaveCount(0)
  } finally {
    await patchSpan(request, novak.id, { start: 34, type: 'pos' })
  }
})

test('the filter counts follow a review of selected annotations that are not on the page (#667)', async ({ page, request }) => {
  const proposals = [fixture.span('lhota_automatic'), fixture.span('praha_automatic')]
  const count = async (status: string) => Number(await page.getByTestId(`concordance-status-count-${status}`).innerText())
  await useViewport(page, 'wide')
  await openWorkspace(page, 'annotator')
  try {
    // Select the proposals, then show only confirmed annotations: the selected ones are off the page.
    await page.getByTestId('concordance-status-pos').click()
    await expect(rows(page)).toHaveCount(2)
    await page.getByTestId('select-all-matches').click()
    await page.getByTestId('concordance-status-pos').click()
    await page.getByTestId('concordance-status-auto').click()
    await expect(page.getByTestId('hidden-selected')).toContainText('2 selected not shown by these filters')
    await expect(page.getByTestId('concordance-status-count-auto')).toHaveText(/\d+/)
    const [auto, rejected] = [await count('auto'), await count('neg')]

    await page.getByTestId('review-reject').click()
    // A change to annotations not on this page asks first.
    await expect(page.getByRole('dialog')).toContainText('2 of them are not on this page')
    await page.getByRole('dialog').getByRole('button', { name: 'Reject 2' }).click()
    await expect(page.getByTestId('review-report')).toContainText('Rejected 2 of 2 annotations.')
    await expect(page.getByTestId('concordance-status-count-auto')).toHaveText(String(auto - 2))
    await expect(page.getByTestId('concordance-status-count-neg')).toHaveText(String(rejected + 2))
  } finally {
    for (const span of proposals) await patchSpan(request, span.id, { type: 'auto' })
  }
})

test('all matches are a fixed selection that a shared user reviews in one batch', async ({ page, request }) => {
  const proposals = [fixture.span('lhota_automatic'), fixture.span('praha_automatic')]
  await useViewport(page, 'wide')
  await openWorkspace(page, 'annotator')
  try {
    // Only the proposals, all selected as they match now.
    await page.getByTestId('concordance-status-pos').click()
    await expect(rows(page)).toHaveCount(2)
    await page.getByTestId('select-all-matches').click()
    await expect(page.getByTestId('concordance-selected')).toHaveText('2 selected')

    // Wider filters show more rows; the selection does not grow.
    await page.getByTestId('concordance-status-pos').click()
    await expect(rows(page)).toHaveCount(4)
    await expect(page.getByTestId('concordance-selected')).toHaveText('2 selected')
    await expect(page.getByTestId('hidden-selected')).toHaveCount(0)

    await page.getByTestId('review-reject').click()
    await expect(page.getByTestId('review-report')).toContainText('Rejected 2 of 2 annotations.')
    // Rejected annotations leave the default filters but stay selected, and the bar says so. Their
    // rows stay, marked, until the list is read again (#690).
    await expect(rows(page)).toHaveCount(4)
    await expect(page.locator('.kwic__row--unmatched')).toHaveCount(2)
    await page.getByTestId('concordance-refresh').click()
    await expect(rows(page)).toHaveCount(2)
    await expect(page.getByTestId('hidden-selected')).toContainText('2 selected not shown by these filters')
    await page.getByTestId('concordance-status-neg').click()
    await expect(row(page, 'Lhoty')).toContainText('Rejected')
    await expect(page.getByTestId('hidden-selected')).toHaveCount(0)

    await page.getByTestId('concordance-status-neg').click()
    await page.getByTestId('deselect-hidden').click()
    await expect(page.getByTestId('concordance-selected')).toHaveCount(0)
    await expect(page.getByTestId('selection-bar')).toContainText('No annotations selected')
  } finally {
    for (const span of proposals) await patchSpan(request, span.id, { type: 'auto' })
  }
})

test('one annotation is reviewed from its source; deleting asks first', async ({ page, request }) => {
  const lhota = fixture.span('lhota_automatic')
  const first = fixture.chunk('chronicle_1').text
  await createSpan(request, 'chronicle_1', 0, 4) // "Roku"
  await useViewport(page, 'narrow')
  await openWorkspace(page)
  const review = page.getByTestId('annotation-review')
  try {
    await row(page, 'Lhoty').click()
    const next = rows(page).nth((await rows(page).locator('.kwic__key-label').allTextContents()).indexOf('Lhoty') + 1)
    await expect(next).toContainText('Confirmed')
    await review.getByRole('button', { name: 'Confirm' }).click()
    await expect(row(page, 'Lhoty')).toContainText('Confirmed')
    // The next row is already decided: the sidebar stays on this one (#690 review).
    await expect(page.getByTestId('annotation-announcement')).toContainText('already reviewed; staying here')
    await expect(row(page, 'Lhoty')).toHaveAttribute('aria-current', 'true')

    await row(page, first.slice(0, 4)).click()
    await panel(page).getByRole('button', { name: 'Delete…' }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click()
    await expect(row(page, first.slice(0, 4))).toHaveCount(1)
    await panel(page).getByRole('button', { name: 'Delete…' }).click()
    await expect(page.getByRole('dialog')).toContainText('cannot be restored')
    await page.getByRole('dialog').getByRole('button', { name: 'Delete 1' }).click()
    await expect(page.getByTestId('review-report')).toContainText('Deleted 1 of 1 annotation.')
    await expect(row(page, first.slice(0, 4))).toHaveCount(0)
    await expect(panel(page).getByTestId('annotation-context-gone')).toBeVisible()
  } finally {
    await patchSpan(request, lhota.id, { type: 'auto' })
  }
})

test('the sidebar names who changed the open annotation and refuses a review of an outdated copy', async ({ page, request }) => {
  const lhota = fixture.span('lhota_automatic')
  await useViewport(page, 'narrow')
  await openWorkspace(page)
  const context = page.getByTestId('annotation-context')
  try {
    await row(page, 'Lhoty').click()
    // Seeded before provenance was recorded.
    await expect(context.getByTestId('provenance-unknown')).toBeVisible()

    // The shared annotator approves it meanwhile; this page still shows the proposal.
    await patchSpan(request, lhota.id, { type: 'pos' }, 'annotator')
    await context.getByRole('button', { name: 'Reject' }).click()
    const conflict = context.getByTestId('annotation-conflict')
    await expect(conflict).toContainText('now confirmed')
    await expect(conflict).toContainText('Your reject was not saved.')
    await expect(context.getByTestId('provenance-reviewed')).toContainText('Confirmed by')
    await expect(row(page, 'Lhoty')).toContainText('Confirmed')

    // Rejecting the version shown now is the user's explicit choice.
    await conflict.getByRole('button', { name: 'Apply to current version' }).click()
    // A single decision adds no report or Undo line above the list (#690 review).
    await expect(page.getByTestId('annotation-announcement')).toContainText('Rejected.')
    await expect(page.getByTestId('review-report')).toHaveCount(0)
    await expect(page.getByTestId('undo-bar')).toHaveCount(0)
    // Rejected: out of the default filters, but the row stays until the list is read again (#690).
    await expect(row(page, 'Lhoty')).toContainText('Rejected')
    await expect(row(page, 'Lhoty')).toHaveClass(/kwic__row--unmatched/)
    await page.getByTestId('concordance-refresh').click()
    await expect(row(page, 'Lhoty')).toHaveCount(0)
  } finally {
    await patchSpan(request, lhota.id, { type: 'auto' })
  }
})

test('a refused review keeps its conflict when the change took the annotation out of the filters', async ({ page, request }) => {
  const lhota = fixture.span('lhota_automatic')
  await useViewport(page, 'wide')
  await openWorkspace(page)
  const context = page.getByTestId('annotation-context')
  try {
    await page.getByTestId('concordance-status-pos').click() // proposals only
    await row(page, 'Lhoty').click()

    // The shared annotator approves it meanwhile: the page read again no longer lists it.
    await patchSpan(request, lhota.id, { type: 'pos' }, 'annotator')
    await context.getByRole('button', { name: 'Reject' }).click()
    const conflict = context.getByTestId('annotation-conflict')
    await expect(conflict).toContainText('now confirmed')
    // The row stays where it was, at its current state, marked as out of the filters (#690).
    await expect(conflict).toContainText('It no longer matches the filters.')
    await expect(row(page, 'Lhoty')).toContainText('Confirmed')
    await expect(row(page, 'Lhoty')).toHaveClass(/kwic__row--unmatched/)
    await expect(context.getByTestId('annotation-context-gone')).toHaveCount(0)

    await conflict.getByRole('button', { name: 'Apply to current version' }).click()
    // A single decision adds no report or Undo line above the list (#690 review).
    await expect(page.getByTestId('annotation-announcement')).toContainText('Rejected.')
    await expect(page.getByTestId('review-report')).toHaveCount(0)
    await expect(page.getByTestId('undo-bar')).toHaveCount(0)
    await expect(row(page, 'Lhoty')).toContainText('Rejected')
  } finally {
    await patchSpan(request, lhota.id, { type: 'auto' })
  }
})

test('a batch review leaves annotations changed since they were selected and can select them', async ({ page, request }) => {
  const proposals = [fixture.span('lhota_automatic'), fixture.span('praha_automatic')]
  await useViewport(page, 'wide')
  await openWorkspace(page, 'annotator')
  try {
    await page.getByTestId('concordance-status-pos').click()
    await expect(rows(page)).toHaveCount(2)
    await page.getByTestId('select-all-matches').click()
    await expect(page.getByTestId('concordance-selected')).toHaveText('2 selected')

    // The owner retags one of them after it was selected.
    await patchSpan(request, proposals[0].id, { tagId: fixture.tag('person').id })
    await page.getByTestId('review-reject').click()
    const report = page.getByTestId('review-report')
    await expect(report).toContainText('Rejected 1 of 2 annotations.')
    await expect(report).toContainText('1 was changed by someone else since you selected it; not saved.')
    await expect(page.getByTestId('review-retry')).toHaveCount(0)

    await page.getByTestId('review-show-changed').click()
    await expect(page.getByTestId('concordance-selected')).toHaveText('1 selected')
    await expect(row(page, 'Lhoty').getByRole('checkbox')).toBeChecked()
    await expect(row(page, 'Lhoty')).toContainText('Proposal')
  } finally {
    await patchSpan(request, proposals[0].id, { tagId: fixture.tag('place').id, type: 'auto' })
    await patchSpan(request, proposals[1].id, { type: 'auto' })
  }
})

// ── Boundary editing in the sidebar and undo (#461) ──

/** Selects the text between two offsets of chunks shown in the sidebar's passage. */
async function selectPassage (page: Page, from: [string, number], to: [string, number]) {
  await page.evaluate(([a, b]) => {
    const point = ([chunkId, offset]: [string, number]): [Node, number] => {
      const text = document.querySelector(`[data-chunk-id="${chunkId}"] [data-chunk-text]`)
      if (!text) throw new Error(`chunk ${chunkId} is not shown`)
      const walker = document.createTreeWalker(text, NodeFilter.SHOW_TEXT)
      let left = offset
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const length = node.textContent?.length ?? 0
        if (left <= length) return [node, left]
        left -= length
      }
      throw new Error('offset past the chunk')
    }
    const range = document.createRange()
    range.setStart(...point(a))
    range.setEnd(...point(b))
    const selection = window.getSelection()
    selection?.removeAllRanges()
    selection?.addRange(range)
  }, [from, to] as const)
}

test('boundaries are edited from the sidebar by keyboard or selection and each edit can be undone', async ({ page, request }) => {
  const brno = fixture.span('brno_manual')
  const first = fixture.chunk('chronicle_1')
  const second = fixture.chunk('chronicle_2')
  await useViewport(page, 'wide')
  await openWorkspace(page)
  const context = page.getByTestId('annotation-context')
  const editor = context.getByTestId('boundary-editor')
  try {
    await row(page, 'Brně').click()
    await context.getByRole('button', { name: 'Edit boundaries' }).click()
    // By keyboard: the editor takes focus; one word earlier, then the end one word later.
    await expect(editor.getByRole('button', { name: 'Move the start one word earlier' })).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(editor.getByTestId('boundary-preview')).toHaveText('v Brně')
    await page.keyboard.press('Tab')
    await page.keyboard.press('Tab')
    await page.keyboard.press('Tab')
    await expect(editor.getByRole('button', { name: 'Move the end one word later' })).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(editor.getByTestId('boundary-preview')).toHaveText('v Brně konala')
    await expect(panel(page).locator('.chunk-context__mark--pending')).toHaveText('v Brně konala')
    await editor.getByRole('button', { name: 'Save boundaries' }).click()

    await expect(editor).toHaveCount(0)
    await expect(row(page, 'v Brně konala')).toHaveAttribute('data-annotation-id', brno.id)
    await expect(context.getByTestId('annotation-context-text')).toHaveText('v Brně konala')
    await expect(page.getByTestId('undo-bar')).toContainText('you changed the boundaries of 1 annotation')

    // By selection, starting in the previous chunk: the annotation moves there (#436).
    await context.getByRole('button', { name: 'Edit boundaries' }).click()
    const jelena = first.text.indexOf('jelena.')
    await selectPassage(page, [first.id, jelena], [second.id, 'Kronikář'.length])
    await editor.getByRole('button', { name: 'Use selected text' }).click()
    await expect(editor.getByTestId('boundary-preview')).toHaveText('jelena.Kronikář')
    await editor.getByRole('button', { name: 'Save boundaries' }).click()
    await expect(editor).toHaveCount(0)
    await expect(panel(page).getByTestId('chunk-context-mark')).toHaveText(['jelena.', 'Kronikář'])
    await expect(rows(page).and(page.locator(`[data-annotation-id="${brno.id}"]`))).toContainText('jelena.')

    // Undo puts back the range before the last edit, on the chunk it was on.
    await page.getByTestId('undo').click()
    await expect(page.getByTestId('review-report')).toContainText('Undo: restored 1 of 1 annotation.')
    await expect(row(page, 'v Brně konala')).toHaveAttribute('data-annotation-id', brno.id)
    await expect(panel(page).getByTestId('chunk-context-mark')).toHaveText('v Brně konala')
    await expect(page.getByTestId('undo')).toHaveCount(0)
  } finally {
    await patchSpan(request, brno.id, { chunkId: second.id, start: 29, end: 33 })
  }
})

test('a boundary edit of an annotation changed meanwhile is refused, then saved on request', async ({ page, request }) => {
  const brno = fixture.span('brno_manual')
  await useViewport(page, 'narrow')
  await openWorkspace(page)
  const context = page.getByTestId('annotation-context')
  const editor = context.getByTestId('boundary-editor')
  try {
    await row(page, 'Brně').click()
    await context.getByRole('button', { name: 'Edit boundaries' }).click()
    await editor.getByRole('button', { name: 'Move the start one word earlier' }).click()
    // The shared annotator retags it meanwhile.
    await patchSpan(request, brno.id, { tagId: fixture.tag('person').id }, 'annotator')
    await editor.getByRole('button', { name: 'Save boundaries' }).click()

    const conflict = context.getByTestId('annotation-conflict')
    await expect(conflict).toContainText('Your boundary change was not saved.')
    await expect(row(page, 'Brně')).toHaveAttribute('data-annotation-id', brno.id)
    await expect(editor.getByTestId('boundary-preview')).toHaveText('v Brně')

    await conflict.getByRole('button', { name: 'Apply to current version' }).click()
    await expect(row(page, 'v Brně')).toHaveAttribute('data-annotation-id', brno.id)
    await expect(conflict).toHaveCount(0)
    // Escape leaves a new edit without saving.
    await context.getByRole('button', { name: 'Edit boundaries' }).click()
    await page.keyboard.press('Escape')
    await expect(editor).toHaveCount(0)
  } finally {
    await patchSpan(request, brno.id, { start: 29, end: 33, tagId: fixture.tag('place').id })
  }
})

test('undoing a batch approval restores the proposals not changed since; a deletion has no undo', async ({ page, request }) => {
  const [lhota, praha] = [fixture.span('lhota_automatic'), fixture.span('praha_automatic')]
  await createSpan(request, 'chronicle_1', 0, 4) // "Roku"
  await useViewport(page, 'wide')
  await openWorkspace(page, 'annotator')
  try {
    await page.getByTestId('concordance-status-pos').click() // proposals only
    await page.getByTestId('select-all-matches').click()
    await page.getByTestId('review-approve').click()
    await expect(page.getByTestId('review-report')).toContainText('Confirmed 2 of 2 annotations.')
    await expect(page.getByTestId('undo-bar')).toContainText('Last change: you confirmed 2 annotations.')

    // The owner rejects one of them meanwhile.
    await patchSpan(request, praha.id, { type: 'neg' })
    await page.getByTestId('undo').click()
    const report = page.getByTestId('review-report')
    await expect(report).toContainText('Undo: restored 1 of 2 annotations.')
    await expect(report).toContainText('1 was changed again since then; not restored.')
    await expect(row(page, 'Lhoty')).toContainText('Proposal')
    await expect(page.getByTestId('undo')).toHaveCount(0)

    await page.getByTestId('concordance-status-pos').click() // all statuses again
    await row(page, 'Roku').click()
    await page.getByTestId('annotation-context').getByRole('button', { name: 'Delete…' }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Delete 1' }).click()
    await expect(page.getByTestId('undo-bar')).toHaveText('Deleted annotations cannot be restored.')
    await expect(page.getByTestId('undo')).toHaveCount(0)
  } finally {
    for (const span of [lhota, praha]) await patchSpan(request, span.id, { type: 'auto' })
  }
})

test('the selection, outside the filters too, and the filter matches download as CSV (#719)', async ({ page }) => {
  await useViewport(page, 'wide')
  await openWorkspace(page)
  /** The rows of a downloaded file of simple cells (no quoted commas or line breaks in this fixture). */
  const csvRows = async (download: Download): Promise<Record<string, string>[]> => {
    const bytes: Uint8Array = readFileSync(await download.path())
    expect([...bytes.subarray(0, 3)], 'UTF-8 byte order mark').toEqual([0xef, 0xbb, 0xbf])
    const [header, ...lines] = new TextDecoder().decode(bytes.subarray(3)).trimEnd().split('\r\n')
    const columns = header.split(',')
    return lines.map((line: string) => Object.fromEntries(line.split(',').map((cell: string, i: number) => [columns[i], cell])))
  }

  // The two proposals selected, then shown only the confirmed annotations: both selected are hidden.
  await page.getByTestId('concordance-status-pos').click()
  await expect(rows(page)).toHaveCount(2)
  await page.getByTestId('select-all-matches').click()
  await expect(page.getByTestId('concordance-selected')).toHaveText('2 selected')
  await page.getByTestId('concordance-status-pos').click()
  await page.getByTestId('concordance-status-auto').click()
  await expect(rows(page)).toHaveCount(2)
  await expect(page.getByTestId('hidden-selected')).toContainText('2 selected not shown')

  await page.getByTestId('export-csv').click()
  const dialog = page.getByTestId('export-dialog')
  await expect(dialog.getByTestId('export-scope-selection')).toHaveAttribute('aria-checked', 'true')
  await expect(dialog.getByTestId('export-hidden-selected')).toContainText('2 of them are not shown by the current filters')
  await expect(dialog.getByTestId('export-target')).toHaveText('Exports 2 selected annotations.')
  let downloading = page.waitForEvent('download')
  await dialog.getByTestId('export-download').click()
  const selected = await csvRows(await downloading)
  expect(selected.map(r => [r.text, r.status]).sort()).toEqual([['Lhoty', 'proposal'], ['Prahy', 'proposal']])
  expect(selected.every(r => r.document_id && r.document_start_char !== '')).toBe(true)
  await expect(dialog.getByTestId('export-result')).toContainText('2 annotations (selected annotations)')

  // The current filters: every confirmed annotation, not the selection.
  await dialog.getByTestId('export-scope-filters').click()
  await expect(dialog.getByTestId('export-filter-summary')).toContainText('Status: Confirmed')
  downloading = page.waitForEvent('download')
  await dialog.getByTestId('export-download').click()
  const matches = await csvRows(await downloading)
  expect(matches.map(r => r.status)).toEqual(['confirmed', 'confirmed'])
  expect((await downloading).suggestedFilename()).toMatch(/^annotations-filters-\d{4}-\d{2}-\d{2}\.csv$/)
  await dialog.getByRole('button', { name: 'Close' }).last().click()
  await expect(dialog).toHaveCount(0)
})
