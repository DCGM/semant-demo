import { expect, test, type Page, type TestInfo } from '@playwright/test'
import { annotation, answerChat, askChat, chatSource, closePhoneNavigation, ensureLoggedIn, fixture, search } from '../e2e/support'

// UI review captures (`scripts/e2e-dev.sh capture`), not part of `make test-e2e`. The
// capture projects in playwright.config.ts run this file at wide desktop, narrow desktop
// and phone widths; each view is saved as test-results/ui-capture/<view>-<project>.png.
// At the narrow desktop width both sidebars must be open, as reviewed in #256/#272.

async function save (page: Page, testInfo: TestInfo, view: string) {
  const file = `${testInfo.project.outputDir}/ui-capture/${view}-${testInfo.project.name}.png`
  // The viewport as a user sees it (a full-page shot cuts the fixed sidebars off).
  await page.screenshot({ path: file })
}

/** Waits until the right sidebar has slid in completely (it is animated). */
async function expectRightSidebarIn (page: Page) {
  const width = page.viewportSize()?.width ?? 0
  await expect.poll(async () => {
    const box = await page.locator('.q-drawer--right').boundingBox()
    return box ? Math.round(box.x + box.width) : -1
  }).toBe(width)
}

async function expectSidebarsOpen (page: Page, testInfo: TestInfo) {
  if (testInfo.project.name !== 'narrow') return
  await expect(page.locator('.q-drawer--left')).toBeVisible()
  await expect(page.locator('.q-drawer--left')).not.toHaveClass(/q-drawer--mini/)
  await expect(page.locator('.q-drawer--right')).toBeVisible()
  await expect(page.locator('.q-drawer--right')).not.toHaveClass(/q-drawer--mini/)
}

test('search results', async ({ page }, testInfo) => {
  await ensureLoggedIn(page, 'owner')
  await page.reload() // without the sign-in notification
  await search(page, 'Lhota')
  await expectSidebarsOpen(page, testInfo)
  await save(page, testInfo, 'search-results')
})

test('document view', async ({ page }, testInfo) => {
  await ensureLoggedIn(page, 'owner')
  await page.goto(`/#/collections/${fixture.collection('chronicles').id}/documents/${fixture.document('chronicle').id}`)
  await page.reload() // without the sign-in notification
  await expect(annotation(page, 'novak_manual')).toBeVisible()
  await expect(page.locator('.gutter-item')).toHaveCount(2)
  await closePhoneNavigation(page)
  await expectSidebarsOpen(page, testInfo)
  await save(page, testInfo, 'document-view')
})

test('corpus overview', async ({ page }, testInfo) => {
  // A synced store has libraries; the fixture store has none (shown as unavailable).
  await page.route('**/api/analytics/corpus/overview', async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    body.libraries = { available: true, values: [{ value: 'mzk', count: 2 }], other_count: 0, unknown_count: 1 }
    await route.fulfill({ response, json: body })
  })
  await page.goto('/#/corpus')
  await closePhoneNavigation(page)
  await expect(page.getByTestId('corpus-libraries').locator('svg').first()).toBeVisible()
  await save(page, testInfo, 'corpus-overview')
})

test('corpus overview without libraries', async ({ page }, testInfo) => {
  await page.goto('/#/corpus')
  await closePhoneNavigation(page)
  await expect(page.getByTestId('corpus-languages').locator('svg').first()).toBeVisible()
  await page.getByTestId('corpus-libraries').scrollIntoViewIfNeeded()
  await save(page, testInfo, 'corpus-overview-unavailable')
})

test('chat sources', async ({ page }, testInfo) => {
  await answerChat(page, [{
    rag_answer: 'The chronicle describes the arrival of the governor [doc 1] and a fire [doc 2].',
    sources: [chatSource('chronicle_1'), chatSource('chronicle_3'), chatSource('gazette_1')]
  }])
  await page.goto('/#/rag')
  await closePhoneNavigation(page)
  await askChat(page, 'What happened in Lhota?')
  await page.locator('.message-bubble', { hasText: 'The chronicle describes' }).getByText('Sources', { exact: true }).click()
  await expect(page.getByTestId('chat-sources').getByRole('listitem')).toHaveCount(3)
  await expectSidebarsOpen(page, testInfo)
  await expectRightSidebarIn(page)
  await save(page, testInfo, 'chat-sources')

  // On a phone the sources cover the chat.
  if (testInfo.project.name === 'phone') await page.getByRole('button', { name: 'Close sidebar' }).click()
  await page.getByRole('link', { name: '[doc 2]' }).click()
  await expect(page.getByTestId('chunk-context').locator('[aria-current="true"]')).toBeInViewport()
  await expectRightSidebarIn(page)
  await save(page, testInfo, 'chat-source-document')
})
