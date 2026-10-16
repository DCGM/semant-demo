import { expect, test, type Page, type TestInfo } from '@playwright/test'
import { annotation, answerChat, askChat, chatSource, closePhoneNavigation, ensureLoggedIn, fixture, search, sidebarPanelButton } from '../e2e/support'

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

test('document view - summary panel (#249)', async ({ page }, testInfo) => {
  await ensureLoggedIn(page, 'owner')
  await page.goto(`/#/collections/${fixture.collection('chronicles').id}/documents/${fixture.document('chronicle').id}`)
  await page.reload() // without the sign-in notification
  await expect(annotation(page, 'novak_manual')).toBeVisible()
  await closePhoneNavigation(page)
  await expectSidebarsOpen(page, testInfo)
  // On phone the right sidebar is a closed overlay by default; open it to reach the panel.
  if (testInfo.project.name === 'phone') {
    await page.getByRole('button', { name: 'Toggle sidebar' }).click()
  }

  await sidebarPanelButton(page, 'Summary').click()
  await page.getByRole('button', { name: 'Summarize Document' }).click()
  await expect(page.getByTestId('document-summary')).toBeVisible()
  await save(page, testInfo, 'document-view-summary')
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
  await answerChat(page, [
    {
      rag_answer: 'The chronicle describes the arrival of the governor [doc 1] and a fire [doc 2].',
      sources: [chatSource('chronicle_1'), chatSource('chronicle_3')]
    },
    {
      rag_answer: 'The gazette mentions a café [doc 1]; the fire is the same [doc 2].',
      sources: [chatSource('gazette_1'), chatSource('chronicle_3')]
    }
  ])
  await page.goto('/#/rag')
  await closePhoneNavigation(page)
  await askChat(page, 'What happened in Lhota?')
  await askChat(page, 'What is in the gazette?')
  // One click on a citation selects its source: expanded in the list, all its citations marked.
  await page.locator('.message-bubble').getByRole('link', { name: '[S2]', exact: true }).last().click()
  const selected = page.getByTestId('chat-sources').getByRole('listitem', { name: 'Source S2' })
  await expect(selected.locator('[aria-expanded="true"]')).toBeVisible()
  await expectSidebarsOpen(page, testInfo)
  await expectRightSidebarIn(page)
  await save(page, testInfo, 'chat-sources')

  await selected.getByRole('button', { name: 'View source S2 in its document' }).click()
  await expect(page.getByTestId('chunk-context-target-label')).toBeInViewport()
  await expectRightSidebarIn(page)
  await save(page, testInfo, 'chat-source-document')
})
