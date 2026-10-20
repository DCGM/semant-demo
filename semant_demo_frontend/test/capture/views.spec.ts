import { expect, test, type Page, type TestInfo } from '@playwright/test'
import {
  annotation, answerChat, answerGuestQuota, askChat, chatSource, closePhoneNavigation, ensureLoggedIn, fixture, search, selectText,
  sidebarPanelButton
} from '../e2e/support'

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

test('search vector selection', async ({ page }, testInfo) => {
  // The browser-test profile configures two search vectors (#217).
  await page.goto('/#/search')
  await closePhoneNavigation(page)
  await page.getByRole('textbox').first().fill('Lhota')
  await page.getByRole('button', { name: 'Search filters' }).click()
  const select = page.getByTestId('search-vector-select')
  await select.click()
  await expect(page.getByRole('option', { name: /Fake small/ })).toBeVisible()
  await expect(page.locator('.q-menu')).not.toHaveClass(/q-transition/) // fully faded in
  await save(page, testInfo, 'search-vector-options')
  await page.getByRole('option', { name: /Fake small/ }).click()
  await expect(page.locator('.q-menu')).toHaveCount(0)
  await page.getByRole('textbox').first().press('Enter')
  await expect(page.locator('#result-1')).toBeVisible()
  await expect(page.locator('.active-filter-chip', { hasText: 'Embedding: Fake small' })).toBeVisible()
  await save(page, testInfo, 'search-vector-selected')
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

test('document view - popover, bulk bar and create-tag dialog (#379)', async ({ page }, testInfo) => {
  await ensureLoggedIn(page, 'owner')
  await page.goto(`/#/collections/${fixture.collection('chronicles').id}/documents/${fixture.document('chronicle').id}`)
  await page.reload() // without the sign-in notification
  await expect(page.locator('.gutter-item')).toHaveCount(2)
  await closePhoneNavigation(page)
  await expectSidebarsOpen(page, testInfo)

  // The chunk gutter starts hidden; its checkboxes select chunks for the bulk bar.
  await page.locator('button[title="Show/hide chunk gutter"]').click()
  await page.locator('.chunk-checkbox-item').first().click()
  await expect(page.locator('.bulk-action-bar')).toBeVisible()
  const start = fixture.chunk('chronicle_1').text.indexOf('hostinci')
  await selectText(page, 'chronicle_1', start, 'chronicle_1', start + 'hostinci'.length)
  await expect(page.locator('.annotation-popover').getByText('Create new tag')).toBeVisible()
  await save(page, testInfo, 'document-view-popover')

  await page.locator('.annotation-popover').getByText('Create new tag').click()
  await expect(page.locator('.q-dialog').getByLabel('Tag Name')).toBeVisible()
  await expect(page.locator('.q-dialog__inner')).not.toHaveClass(/q-transition/) // fully in
  await save(page, testInfo, 'document-view-create-tag-dialog')
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

// The daily AI allowance (#234): the header indicator and its details, the near-limit warning
// and a refused chat question (the allowance answered by the test, see answerGuestQuota).
test('ai allowance details', async ({ page }, testInfo) => {
  await page.goto('/#/search')
  await closePhoneNavigation(page)
  await page.getByRole('button', { name: /^AI allowance:/ }).click()
  await expect(page.getByTestId('quota-details')).toBeVisible()
  await expect(page.locator('.q-menu')).toHaveCSS('opacity', '1') // faded in
  await save(page, testInfo, 'ai-allowance-details')
})

test('ai allowance near the limit', async ({ page }, testInfo) => {
  await answerGuestQuota(page, 0.21)
  await page.goto('/#/rag')
  await closePhoneNavigation(page)
  await expect(page.getByTestId('quota-banner')).toBeVisible()
  await save(page, testInfo, 'ai-allowance-near-limit')
})

test('ai allowance used up', async ({ page }, testInfo) => {
  const reset = await answerGuestQuota(page, 0.25)
  await page.route('**/api/rag', (route) => route.fulfill({
    status: 429,
    json: {
      detail: 'Insufficient remaining daily AI allowance for this operation.',
      code: 'llm_quota_exhausted',
      principal: 'guest',
      reset_at: reset.toISOString(),
      limit_usd: 0.25,
      used_usd: 0.25
    }
  }))
  await page.goto('/#/rag')
  await closePhoneNavigation(page)
  const input = page.getByPlaceholder('Vaše otázka?')
  await input.fill('What happened in Lhota?')
  await input.press('Enter')
  await expect(page.locator('.message-bubble').last()).toContainText('Today\'s AI allowance has no room')
  await save(page, testInfo, 'ai-allowance-used-up')
})
