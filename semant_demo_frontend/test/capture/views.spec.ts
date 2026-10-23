import { expect, test, type Page, type TestInfo } from '@playwright/test'
import {
  annotation, answerChat, apiToken, deleteAddedSpans, answerGuestQuota, askChat, chatSource, closePhoneNavigation, ensureLoggedIn, fixture, search, selectText,
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

test('annotation workspace (#329)', async ({ page, request }, testInfo) => {
  // A few more annotations than the fixture holds: a repeated name, a long cross-chunk span.
  const headers = { Authorization: `Bearer ${await apiToken(request, 'owner')}` }
  const first = fixture.chunk('chronicle_1').text
  const spans: [string, number, number][] = [
    ['chronicle_1', 34, 43], ['chronicle_1', 10, first.length + 30], ['chronicle_2', 51, 60], ['letters_2', 10, 16]
  ]
  try {
    for (const [chunk, start, end] of spans) {
      const response = await request.post('/api/tag_spans', {
        headers, data: { chunkId: fixture.chunk(chunk).id, tagId: fixture.tag('person').id, start, end, type: 'pos' }
      })
      expect(response.ok()).toBe(true)
    }
    await ensureLoggedIn(page, 'owner')
    await page.goto(`/#/collections/${fixture.collection('chronicles').id}/annotations`)
    await page.reload() // without the sign-in notification
    await closePhoneNavigation(page)
    await expect(page.getByTestId('kwic-row')).toHaveCount(8)
    await page.getByTestId('kwic-row').nth(3).getByRole('checkbox').click()
    await save(page, testInfo, 'annotation-workspace')

    await page.getByTestId('kwic-row').nth(4).click()
    await expect(page.getByTestId('chunk-context-mark').first()).toBeVisible()
    await expectRightSidebarIn(page)
    await expectSidebarsOpen(page, testInfo)
    await save(page, testInfo, 'annotation-workspace-context')
  } finally {
    await deleteAddedSpans(request, 'owner', 'chronicles')
  }
})

test('annotation workspace review (#459)', async ({ page, request }, testInfo) => {
  // A batch reject of the two proposals: its per-item result and the now hidden selection.
  const headers = { Authorization: `Bearer ${await apiToken(request, 'owner')}` }
  const proposals = ['lhota_automatic', 'praha_automatic'].map(key => fixture.span(key).id)
  try {
    await ensureLoggedIn(page, 'owner')
    await page.goto(`/#/collections/${fixture.collection('chronicles').id}/annotations`)
    await page.reload() // without the sign-in notification
    await closePhoneNavigation(page)
    await expect(page.getByTestId('kwic-row')).toHaveCount(4)
    await page.getByTestId('concordance-status-pos').click()
    await expect(page.getByTestId('kwic-row')).toHaveCount(2)
    await page.getByTestId('select-all-matches').click()
    await page.getByTestId('concordance-status-pos').click()
    await expect(page.getByTestId('kwic-row')).toHaveCount(4)
    const novak = page.getByTestId('kwic-row').filter({ has: page.locator('.kwic__key', { hasText: 'Jan Novák' }) })
    await novak.getByRole('checkbox').click()
    await expect(page.getByTestId('concordance-selected')).toHaveText('3 selected')
    await page.mouse.move(0, 0) // no hover tooltip
    await page.waitForTimeout(400) // the checkbox animation
    await save(page, testInfo, 'annotation-review-selection')

    await novak.getByRole('checkbox').click()
    await page.getByTestId('review-reject').click()
    await expect(page.getByTestId('hidden-selected')).toBeVisible()
    await page.mouse.move(0, 0)
    await save(page, testInfo, 'annotation-review-result')

    await page.getByTestId('kwic-row').first().click()
    await expect(page.getByTestId('annotation-review')).toBeVisible()
    await expectRightSidebarIn(page)
    await expectSidebarsOpen(page, testInfo)
    await save(page, testInfo, 'annotation-review-sidebar')
  } finally {
    for (const id of proposals) {
      await request.patch(`/api/tag_spans/${id}`, {
        headers, params: { collection_id: fixture.collection('chronicles').id }, data: { type: 'auto' }
      })
    }
  }
})

test('annotation provenance and edit conflicts (#460)', async ({ page, request }, testInfo) => {
  // The sidebar names who created and changed the open annotation; a review of a copy
  // someone else changed meanwhile is refused, in the sidebar and in a batch.
  const collectionId = fixture.collection('chronicles').id
  const as = async (userKey: string) => ({ Authorization: `Bearer ${await apiToken(request, userKey)}` })
  const patch = async (id: string, data: Record<string, unknown>, userKey = 'owner') =>
    request.patch(`/api/tag_spans/${id}`, { headers: await as(userKey), params: { collection_id: collectionId }, data })
  const lhota = fixture.span('lhota_automatic')
  const praha = fixture.span('praha_automatic')
  const row = (text: string) => page.getByTestId('kwic-row').filter({ has: page.locator('.kwic__key', { hasText: text }) })
  // On a phone the sidebar covers the list.
  const backToList = async () => {
    if (testInfo.project.name === 'phone') await page.getByRole('button', { name: 'Close sidebar' }).click()
  }
  try {
    const created = await (await request.post('/api/tag_spans', {
      headers: await as('owner'),
      data: { chunkId: fixture.chunk('chronicle_1').id, tagId: fixture.tag('person').id, start: 0, end: 4, type: 'pos' }
    })).json() as { id: string }
    await ensureLoggedIn(page, 'owner')
    await page.goto(`/#/collections/${collectionId}/annotations`)
    await page.reload() // without the sign-in notification
    await closePhoneNavigation(page)

    // Created by the owner, then retagged by the shared annotator.
    await patch(created.id, { tagId: fixture.tag('place').id }, 'annotator')
    await page.getByTestId('concordance-status-pos').click() // reload with the change
    await page.getByTestId('concordance-status-pos').click()
    await page.locator(`[data-testid="kwic-row"][data-annotation-id="${created.id}"]`).click()
    await expect(page.getByTestId('provenance-edited')).toBeVisible()
    await expectRightSidebarIn(page)
    await expectSidebarsOpen(page, testInfo)
    await page.mouse.move(0, 0)
    await save(page, testInfo, 'annotation-provenance-sidebar')

    // The annotator approves the proposal the owner has open; the owner's reject is refused.
    await backToList()
    await row('Lhoty').click()
    await patch(lhota.id, { type: 'pos' }, 'annotator')
    await page.getByTestId('annotation-review').getByRole('button', { name: 'Reject' }).click()
    await expect(page.getByTestId('annotation-conflict')).toBeVisible()
    await page.mouse.move(0, 0)
    await save(page, testInfo, 'annotation-conflict-sidebar')

    // A batch: one of the selected proposals changed after it was selected.
    await backToList()
    await patch(lhota.id, { type: 'auto' })
    await page.getByTestId('concordance-status-pos').click()
    await expect(page.getByTestId('kwic-row')).toHaveCount(2)
    await page.getByTestId('select-all-matches').click()
    await patch(praha.id, { tagId: fixture.tag('person').id }, 'annotator')
    await page.getByTestId('review-reject').click()
    await expect(page.getByTestId('review-show-changed')).toBeVisible()
    await page.mouse.move(0, 0)
    await save(page, testInfo, 'annotation-conflict-report')
  } finally {
    await patch(lhota.id, { type: 'auto' })
    await patch(praha.id, { type: 'auto', tagId: fixture.tag('place').id })
    await deleteAddedSpans(request, 'owner', 'chronicles')
  }
})

test('annotation boundary editing and undo (#461)', async ({ page, request }, testInfo) => {
  // The sidebar's boundary editor with the new range marked, then the saved edit with its undo.
  const collectionId = fixture.collection('chronicles').id
  const brno = fixture.span('brno_manual')
  const restore = async () => request.patch(`/api/tag_spans/${brno.id}`, {
    headers: { Authorization: `Bearer ${await apiToken(request, 'owner')}` },
    params: { collection_id: collectionId },
    data: { chunkId: fixture.chunk('chronicle_2').id, start: 29, end: 33 }
  })
  try {
    await ensureLoggedIn(page, 'owner')
    await page.goto(`/#/collections/${collectionId}/annotations`)
    await page.reload() // without the sign-in notification
    await closePhoneNavigation(page)
    await page.locator(`[data-testid="kwic-row"][data-annotation-id="${brno.id}"]`).click()
    await expectRightSidebarIn(page)
    await expectSidebarsOpen(page, testInfo)
    await page.getByRole('button', { name: 'Edit boundaries' }).click()
    const editor = page.getByTestId('boundary-editor')
    await editor.getByRole('button', { name: 'Move the start one word earlier' }).click()
    await editor.getByRole('button', { name: 'Move the end one word later' }).click()
    await expect(editor.getByTestId('boundary-preview')).toHaveText('v Brně konala')
    await page.mouse.move(0, 0)
    await save(page, testInfo, 'annotation-boundary-editor')

    await editor.getByRole('button', { name: 'Save boundaries' }).click()
    await expect(page.getByTestId('undo')).toBeVisible()
    if (testInfo.project.name === 'phone') {
      await page.getByRole('button', { name: 'Close sidebar' }).click()
      // Slid out completely (it is animated).
      await expect.poll(async () => (await page.locator('.q-drawer--right').boundingBox())?.x ?? 0)
        .toBeGreaterThanOrEqual(page.viewportSize()?.width ?? 0)
    }
    await page.mouse.move(0, 0)
    await save(page, testInfo, 'annotation-boundary-undo')
  } finally {
    await restore()
  }
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
