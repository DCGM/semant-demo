import { expect, test, type Page, type TestInfo } from '@playwright/test'
import {
  annotation, answerChat, apiToken, deleteAddedAttributes, deleteAddedSpans, answerGuestQuota, askChat, chatSource, ensureLoggedIn, fixture, search, selectText,
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

test('recent searches', async ({ page }, testInfo) => {
  // #558: the dropdown under the query field, on an empty page and over results.
  await ensureLoggedIn(page, 'owner')
  await search(page, 'Brno')
  const input = page.getByRole('combobox', { name: 'Search query' })
  await input.fill('Lhota')
  await page.getByRole('button', { name: 'Search filters' }).click()
  await page.getByTestId('search-vector-select').click()
  await page.getByRole('option', { name: /Fake small/ }).click()
  await expect(page.locator('.q-menu')).toHaveCount(0)
  await page.getByRole('button', { name: 'Search filters' }).click()
  await input.press('Enter')
  await expect(page.locator('#result-1')).toBeVisible()
  await search(page, 'Kronika obce Lhota a jejích obyvatel v dlouhém dotazu, který se nevejde na jeden řádek')

  await page.reload() // an empty page without the sign-in notification
  await input.click()
  await expect(page.getByTestId('search-history-entry')).toHaveCount(3)
  await save(page, testInfo, 'search-history') // no results yet, so no right sidebar

  await search(page, 'Brno')
  await input.fill('lho')
  await expect(page.getByTestId('search-history-entry')).toHaveCount(2)
  await input.press('ArrowDown')
  await expectSidebarsOpen(page, testInfo)
  await save(page, testInfo, 'search-history-filtered')

  // A history saved by a newer version of the application: the list asks for a reload.
  await page.evaluate(() => {
    const key = Object.keys(localStorage).find(k => k.startsWith('semant.searchHistory.search.')) as string
    localStorage.setItem(key, JSON.stringify({ ...JSON.parse(localStorage.getItem(key) ?? '{}'), criteriaVersion: 99 }))
  })
  await page.reload()
  await input.click()
  await expect(page.getByTestId('search-history-reload')).toBeVisible()
  await save(page, testInfo, 'search-history-newer-version')
})

test('search documents: filter-only and ranked results, Load more and states (#606, #607)', async ({ page }, testInfo) => {
  // A first page of two, so Load more and the coverage line show with the small fixture corpus.
  await page.route('**/api/search/documents', async (route) => {
    const body = route.request().postDataJSON()
    await route.continue({ postData: JSON.stringify(body.offset === 0 ? { ...body, limit: 2 } : body) })
  })
  await page.goto('/#/search?chunk_languages=ces')
  await expect(page.getByTestId('document-result-open')).toHaveCount(2)
  await expect(page.getByTestId('search-load-more')).toBeVisible()
  await page.getByTestId('search-coverage').click() // closes the recent searches the field offers
  // No right sidebar: the Summary panel serves passages only.
  await save(page, testInfo, 'search-documents')

  await page.getByTestId('search-load-more').click()
  await expect(page.getByTestId('document-result-open')).toHaveCount(3)
  await save(page, testInfo, 'search-documents-all')

  // Ranked by a text query (#607): the title match first, each document with its best passage.
  await page.goto('/#/search?q=Lhota&chunk_languages=ces&mode=documents')
  await expect(page.getByTestId('document-result-evidence').first()).toBeVisible()
  await page.getByTestId('search-coverage').click()
  await save(page, testInfo, 'search-documents-ranked')

  await page.goto('/#/search?chunk_classifications=communicative_mode:narration&year_min=1900')
  await expect(page.getByTestId('search-empty')).toBeVisible()
  await page.getByTestId('search-empty').click()
  await save(page, testInfo, 'search-documents-empty')
})

test('search passages: applied filters, coverage, Load more, pending and empty states (#605)', async ({ page }, testInfo) => {
  // Pages of three, so Load more and the coverage line show with the small fixture corpus.
  await page.route('**/api/search/passages', async (route) => {
    await route.continue({ postData: JSON.stringify({ ...route.request().postDataJSON(), limit: 3 }) })
  })
  await page.goto('/#/search?q=Lhota&chunk_languages=ces&year_max=1950')
  await expect(page.locator('#result-1')).toBeVisible()
  await expect(page.getByTestId('search-load-more')).toBeVisible()
  await expectSidebarsOpen(page, testInfo)
  await save(page, testInfo, 'search-passages')

  await page.getByRole('combobox', { name: 'Search query' }).fill('Brno')
  await expect(page.getByTestId('search-pending')).toBeVisible()
  await save(page, testInfo, 'search-passages-pending')

  await page.goto('/#/search?chunk_languages=ces&mode=passages')
  await expect(page.getByTestId('search-needs-query')).toBeVisible()
  await page.getByTestId('search-needs-query').click() // closes the recent searches the field offers
  await expect(page.getByTestId('search-history')).toHaveCount(0)
  await save(page, testInfo, 'search-passages-needs-query')

  await page.goto('/#/search?q=Lhota&chunk_classifications=complexity:expert&chunk_languages=zxx')
  await expect(page.getByTestId('search-empty')).toBeVisible()
  await save(page, testInfo, 'search-passages-empty')

  await page.unroute('**/api/search/passages')
  await page.route('**/api/search/passages', (route) => route.fulfill({
    status: 422, json: { detail: 'Passages cannot be filtered by complexity: this corpus database is not recorded.' }
  }))
  await page.goto('/#/search?q=Brno')
  await expect(page.getByTestId('search-error')).toBeVisible()
  await save(page, testInfo, 'search-passages-error')
})

test('search vector selection', async ({ page }, testInfo) => {
  // The browser-test profile configures two search vectors (#217).
  await page.goto('/#/search')
  await page.getByRole('combobox', { name: 'Search query' }).fill('Lhota')
  await page.getByRole('button', { name: 'Search filters' }).click()
  const select = page.getByTestId('search-vector-select')
  await select.click()
  await expect(page.getByRole('option', { name: /Fake small/ })).toBeVisible()
  await expect(page.locator('.q-menu')).not.toHaveClass(/q-transition/) // fully faded in
  await save(page, testInfo, 'search-vector-options')
  await page.getByRole('option', { name: /Fake small/ }).click()
  await expect(page.locator('.q-menu')).toHaveCount(0)
  await page.getByRole('combobox', { name: 'Search query' }).press('Enter')
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
  await expectSidebarsOpen(page, testInfo)
  await save(page, testInfo, 'document-view')
})

test('document view - summary panel (#249)', async ({ page }, testInfo) => {
  await ensureLoggedIn(page, 'owner')
  await page.goto(`/#/collections/${fixture.collection('chronicles').id}/documents/${fixture.document('chronicle').id}`)
  await page.reload() // without the sign-in notification
  await expect(annotation(page, 'novak_manual')).toBeVisible()
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

/** Lets the fixture store look synced: it has no library property, a synced store has one. */
async function withLibraries (page: Page) {
  await page.route('**/api/analytics/corpus/distributions', async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    body.libraries = { available: true, values: [{ value: 'mzk', count: 2 }], other_count: 0, unknown_count: 1 }
    await route.fulfill({ response, json: body })
  })
  await page.route('**/api/analytics/corpus/library-years', (route) => route.fulfill({
    json: {
      scope: 'searchable_corpus',
      unit: 'documents',
      filters: { year_min: null, year_max: null, title_contains: [], libraries: [], languages: [] },
      total_documents: 3,
      computed_at: '2026-10-22T12:00:00Z',
      available: true,
      rows: [
        { library: 'mzk', kind: 'value', total_documents: 2, years: [{ year: 1851, count: 1 }, { year: 1902, count: 1 }], unknown_year_count: 0 },
        { library: null, kind: 'unknown', total_documents: 1, years: [], unknown_year_count: 1 }
      ]
    }
  }))
}

test('collection attributes (#331, #506, #522)', async ({ page, request }, testInfo) => {
  const headers = { Authorization: `Bearer ${await apiToken(request, 'owner')}` }
  const base = `/api/user_collections/${fixture.collection('chronicles').id}/attributes`
  // A realistic large attribute: ~100 values (one retired), a long description, Unknown.
  const topics = ['economy', 'elections', 'migration', 'health', 'education', 'agriculture', 'railways', 'taxes',
    'church', 'schools', 'army', 'weather', 'harvest', 'fires', 'floods', 'trade', 'crafts', 'markets', 'courts', 'police']
  const attributes = [
    {
      name: 'Speaker type',
      description: 'Who says the quoted words, as the source presents them.',
      cardinality: 'single',
      tag_ids: [fixture.tag('person').id],
      values: [
        { label: 'politician', description: 'Holds or seeks a public office.' },
        { label: 'journalist' },
        { label: 'chronicler' },
        { label: 'Unknown', kind: 'unknown' }
      ]
    },
    {
      name: 'Topic',
      description: Array.from({ length: 8 }, (_, i) =>
        `Guideline ${i + 1}: choose every topic the passage discusses at some length, not those it only mentions in passing.`).join('\n'),
      cardinality: 'multi',
      all_tags: true,
      values: [
        ...Array.from({ length: 99 }, (_, i) => ({ label: `${topics[i % topics.length]}${i >= topics.length ? ` ${Math.floor(i / topics.length) + 1}` : ''}` })),
        { label: 'Not applicable', kind: 'not_applicable' }
      ]
    },
    // Applies to no tag (#522): Selected tags with none, distinct from All tags.
    { name: 'Source reliability', cardinality: 'single', tag_ids: [], values: [{ label: 'reliable' }] }
  ]
  try {
    for (const data of attributes) expect((await request.post(base, { headers, data })).ok()).toBe(true)
    const listed = await (await request.get(base, { headers })).json() as { id: string, name: string, values: { id: string, label: string }[] }[]
    const speaker = listed.find(a => a.name === 'Speaker type')!
    const chronicler = speaker.values.find(v => v.label === 'chronicler')!
    expect((await request.patch(`${base}/${speaker.id}/values/${chronicler.id}`, { headers, data: { retired: true } })).ok()).toBe(true)

    await ensureLoggedIn(page, 'owner')
    await page.goto(`/#/collections/${fixture.collection('chronicles').id}/attributes`)
    await page.reload() // without the sign-in notification
    await expect(page.getByTestId('attribute')).toHaveCount(3)
    await save(page, testInfo, 'attributes')

    const topic = page.getByTestId('attribute').filter({ hasText: 'Topic' })
    await topic.getByRole('button', { name: /^\+\d+ more$/ }).click()
    await save(page, testInfo, 'attributes-expanded')
    await topic.getByRole('button', { name: 'Show less' }).click()

    await page.getByLabel('Search attributes and values').fill('elect')
    await expect(page.getByTestId('attribute')).toHaveCount(1)
    await save(page, testInfo, 'attributes-search')
    await page.getByLabel('Search attributes and values').fill('')
    await expect(page.getByTestId('attribute')).toHaveCount(3)

    await page.getByRole('button', { name: 'Edit Topic' }).click()
    await expect(page.locator('.q-dialog .q-card')).toBeVisible()
    await save(page, testInfo, 'attribute-edit-dialog')
    await page.getByRole('dialog').getByTestId('attribute-values-editor').scrollIntoViewIfNeeded()
    await save(page, testInfo, 'attribute-edit-values')
    await page.getByRole('dialog').getByRole('button', { name: 'Cancel', exact: true }).click()

    await page.getByTestId('attribute-create').click()
    await page.getByLabel('Name').fill('Stance')
    await page.getByRole('dialog').getByRole('checkbox', { name: 'Allow multiple values per annotation' }).click()
    await page.getByLabel('Value 1', { exact: true }).fill('for')
    await page.getByRole('button', { name: 'Add value', exact: true }).click()
    await page.getByLabel('Value 2', { exact: true }).fill('against')
    await page.getByRole('dialog').getByRole('radio', { name: 'Selected tags' }).click()
    await page.keyboard.press('Tab') // a focused field's label is still floating up
    await expect(page.locator('.q-dialog .q-card')).toBeVisible()
    await save(page, testInfo, 'attribute-create-dialog')
    await page.getByRole('dialog').getByRole('button', { name: 'Cancel', exact: true }).click()
    await page.getByRole('button', { name: 'Yes' }).click()

    await page.getByRole('tab', { name: 'Tags', exact: true }).click()
    await expect(page.getByTestId('tag-attribute').first()).toBeVisible()
    await save(page, testInfo, 'tags-attributes')
  } finally {
    await deleteAddedAttributes(request, 'owner', 'chronicles')
  }
})

test('attribute name taken (#331)', async ({ page, request }, testInfo) => {
  // A taken name is shown at the Name field, which gets the focus, however the form is scrolled.
  const headers = { Authorization: `Bearer ${await apiToken(request, 'owner')}` }
  const created = await request.post(`/api/user_collections/${fixture.collection('chronicles').id}/attributes`, {
    headers, data: { name: 'Role', cardinality: 'single', all_tags: true, values: [{ label: 'statesman' }] }
  })
  expect(created.ok()).toBe(true)
  try {
    await ensureLoggedIn(page, 'owner')
    await page.goto(`/#/collections/${fixture.collection('chronicles').id}/attributes`)
    await page.reload() // without the sign-in notification
    await page.getByTestId('attribute-create').click()
    const dialog = page.getByRole('dialog')
    await dialog.getByLabel('Name').fill('role')
    await dialog.getByRole('textbox', { name: 'Value 1', exact: true }).fill('statesman')
    await dialog.getByRole('button', { name: 'Add value' }).click()
    await dialog.getByRole('textbox', { name: 'Value 2', exact: true }).fill('Statesman')
    await dialog.getByRole('button', { name: 'Create' }).click()
    await expect(dialog.getByLabel('Name')).toBeFocused()
    await expect(dialog).toContainText('An attribute named "Role" already exists in this collection.')
    await save(page, testInfo, 'attribute-name-taken')
  } finally {
    await deleteAddedAttributes(request, 'owner', 'chronicles')
  }
})

test('attribute assignment in the workspace (#331)', async ({ page, request }, testInfo) => {
  // The Role column with values on the confirmed row, its picker, the batch dialog, the per-item
  // result of a selection and the sidebar's attributes of the open annotation.
  const headers = { Authorization: `Bearer ${await apiToken(request, 'owner')}` }
  const base = `/api/user_collections/${fixture.collection('chronicles').id}`
  const created = await request.post(`${base}/attributes`, {
    headers,
    data: {
      name: 'Role',
      cardinality: 'multi',
      tag_ids: [fixture.tag('person').id],
      values: [{ label: 'statesman' }, { label: 'chronicler' }, { label: 'witness' }, { label: 'Unknown', kind: 'unknown' }]
    }
  })
  expect(created.ok()).toBe(true)
  const place = await request.post(`${base}/attributes`, {
    headers, data: { name: 'Place type', cardinality: 'single', all_tags: true, values: [{ label: 'town' }, { label: 'village' }] }
  })
  expect(place.ok()).toBe(true)
  try {
    await ensureLoggedIn(page, 'owner')
    await page.goto(`/#/collections/${fixture.collection('chronicles').id}/annotations`)
    await page.reload() // without the sign-in notification
    await expect(page.getByTestId('kwic-row')).toHaveCount(4)
    // Two columns side by side (#537).
    await page.getByTestId('concordance-show-attribute').click()
    await page.getByRole('option', { name: 'Role', exact: true }).click()
    await page.getByRole('option', { name: 'Place type', exact: true }).click()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('listbox')).toHaveCount(0)
    const novak = page.getByTestId('kwic-row').filter({ has: page.locator('.kwic__key', { hasText: 'Jan Novák' }) })
    const role = novak.locator(`[data-testid="kwic-attribute"][data-attribute-id="${(await created.json()).id}"]`)
    const placeType = novak.locator(`[data-testid="kwic-attribute"][data-attribute-id="${(await place.json()).id}"]`)
    const picker = page.getByTestId('attribute-value-picker')
    await placeType.getByTestId('kwic-attribute-edit').click()
    await picker.getByText('town', { exact: true }).click()
    await expect(placeType.getByTestId('attribute-chips')).toHaveText('town')
    await expect(picker).toHaveCount(0)
    await role.getByTestId('kwic-attribute-edit').click()
    await picker.getByText('statesman', { exact: true }).click()
    await expect(role.getByTestId('attribute-chips')).toHaveText('statesman')
    await picker.getByText('witness', { exact: true }).click()
    await expect(role.getByTestId('attribute-chips')).toHaveText('statesmanwitness')
    await expect(page.locator('.q-menu')).not.toHaveClass(/q-transition/)
    await save(page, testInfo, 'attribute-assign-column')
    await page.keyboard.press('Escape')
    // A list narrower than its columns scrolls sideways under the checkbox and annotation (#537).
    const kwic = page.getByTestId('kwic')
    if (await kwic.evaluate(el => el.scrollWidth > el.clientWidth)) {
      await expect(page.getByTestId('attribute-value-picker')).toHaveCount(0)
      await kwic.evaluate(el => { el.scrollLeft = el.scrollWidth })
      await page.mouse.move(0, 0)
      await save(page, testInfo, 'attribute-assign-column-scrolled')
      await kwic.evaluate(el => { el.scrollLeft = 0 })
    }

    await page.getByTestId('select-all-matches').click()
    await page.getByTestId('assign-attribute').click()
    const dialog = page.getByRole('dialog')
    await dialog.getByTestId('assign-dialog-attribute').click()
    await page.getByRole('option', { name: 'Role (several values)' }).click()
    await expect(page.locator('.q-menu')).toHaveCount(0)
    await dialog.getByRole('checkbox', { name: 'chronicler' }).click()
    await expect(dialog.getByTestId('assign-summary')).toContainText('Add "chronicler"')
    await save(page, testInfo, 'attribute-assign-dialog')
    await dialog.getByRole('button', { name: 'Add to 4' }).click()
    await expect(page.getByTestId('assign-report')).toContainText('saved 1 of 4')
    await expect(dialog).toHaveCount(0)
    await page.mouse.move(0, 0)
    await save(page, testInfo, 'attribute-assign-result')

    await novak.locator('.kwic__key').click() // not on an attribute cell, which edits instead
    await expect(page.getByTestId('annotation-attributes')).toBeVisible()
    await expectRightSidebarIn(page)
    await expectSidebarsOpen(page, testInfo)
    await save(page, testInfo, 'attribute-assign-sidebar')
  } finally {
    await deleteAddedAttributes(request, 'owner', 'chronicles')
  }
})

test('applicable attributes in Create/Edit Tag (#516)', async ({ page, request }, testInfo) => {
  // Create Tag lists the Selected tags attributes to switch and the All tags ones locked on; a
  // refused removal of the tag from an attribute is shown at that attribute.
  const base = `/api/user_collections/${fixture.collection('chronicles').id}`
  const headers = { Authorization: `Bearer ${await apiToken(request, 'owner')}` }
  const person = fixture.tag('person')
  for (const data of [
    { name: 'Speaker type', tag_ids: [person.id], values: [{ label: 'politician' }] },
    { name: 'Mood', tag_ids: [], values: [{ label: 'calm' }] },
    { name: 'Tone of an unusually long attribute name that has to wrap', tag_ids: [], values: [{ label: 'formal' }] },
    { name: 'Topic', all_tags: true, values: [{ label: 'elections' }] }
  ]) {
    expect((await request.post(`${base}/attributes`, { headers, data })).ok()).toBe(true)
  }
  const speaker = (await (await request.get(`${base}/attributes`, { headers })).json() as { id: string, name: string, values: { id: string }[] }[])
    .find(a => a.name === 'Speaker type')!
  const novak = fixture.span('novak_manual').id
  const rows = await request.get(`${base}/annotations`, { headers, params: { annotation_id: novak } })
  const assigned = await request.post(`${base}/annotations/attributes/assign`, {
    headers,
    data: {
      attribute_id: speaker.id,
      annotation_ids: [novak],
      mode: 'replace',
      value_ids: [speaker.values[0]!.id],
      expected_versions: { [novak]: (await rows.json()).rows[0].attributeVersion }
    }
  })
  expect((await assigned.json()).outcome).toBe('complete')
  try {
    await ensureLoggedIn(page, 'owner')
    await page.goto(`/#/collections/${fixture.collection('chronicles').id}/tags`)
    await page.reload() // without the sign-in notification
    const dialog = page.getByRole('dialog')
    const toggle = (name: string) => dialog.getByTestId('tag-applicable-attribute').filter({ hasText: name }).getByRole('switch')

    await page.getByRole('button', { name: 'Create' }).first().click()
    await dialog.getByLabel('Tag Name').fill('Speaker')
    await dialog.getByLabel('Tag Shorthand').fill('SPK')
    await toggle('Mood').click()
    await dialog.getByTestId('tag-applicable-attributes').scrollIntoViewIfNeeded()
    await save(page, testInfo, 'tag-create-applicable-attributes')
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
    await page.getByRole('button', { name: 'Yes' }).click()

    const row = page.locator('tbody tr').filter({ has: page.getByText(person.name, { exact: true }) })
    await row.getByRole('button', { name: 'Edit tag' }).click()
    await toggle('Speaker type').click()
    await dialog.getByRole('button', { name: 'Save', exact: true }).click()
    await expect(dialog.getByTestId('tag-applicable-attribute-error')).toContainText('1 annotations')
    await dialog.getByTestId('tag-applicable-attribute-error').scrollIntoViewIfNeeded()
    await save(page, testInfo, 'tag-edit-refused-attribute')
  } finally {
    await deleteAddedAttributes(request, 'owner', 'chronicles')
  }
})

test('corpus overview', async ({ page }, testInfo) => {
  await withLibraries(page)
  await page.goto('/#/corpus')
  await expect(page.getByTestId('corpus-libraries').locator('svg').first()).toBeVisible()
  await save(page, testInfo, 'corpus-overview')
})

test('corpus overview filtered, with timeline and heatmap', async ({ page }, testInfo) => {
  await withLibraries(page)
  await page.goto('/#/corpus')
  await page.getByTestId('filter-title').fill('kronika')
  await page.getByTestId('filter-title').press('Enter')
  await page.getByTestId('filter-title').fill('dopisy')
  await page.getByTestId('filter-title').press('Enter')
  await expect(page.getByTestId('corpus-total')).toHaveText('2')
  await save(page, testInfo, 'corpus-filtered')
  await page.getByTestId('heatmap-show').click()
  await expect(page.getByTestId('corpus-heatmap').locator('svg').first()).toBeVisible()
  await page.getByTestId('corpus-years').scrollIntoViewIfNeeded()
  await save(page, testInfo, 'corpus-timeline-heatmap')
})

test('corpus overview without libraries', async ({ page }, testInfo) => {
  await page.goto('/#/corpus')
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
  await page.getByRole('button', { name: /^AI allowance:/ }).click()
  await expect(page.getByTestId('quota-details')).toBeVisible()
  await expect(page.locator('.q-menu')).toHaveCSS('opacity', '1') // faded in
  await save(page, testInfo, 'ai-allowance-details')
})

test('ai allowance near the limit', async ({ page }, testInfo) => {
  await answerGuestQuota(page, 0.21)
  await page.goto('/#/rag')
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
  const input = page.getByPlaceholder('Vaše otázka?')
  await input.fill('What happened in Lhota?')
  await input.press('Enter')
  await expect(page.locator('.message-bubble').last()).toContainText('Today\'s AI allowance has no room')
  await save(page, testInfo, 'ai-allowance-used-up')
})

test('scan viewer', async ({ page }, testInfo) => {
  // The scan viewer preview (#543) with a selected line, a highlighted page in the strip and
  // a zoomed page; the synthetic page fixtures of the profile.
  const chronicle = fixture.document('chronicle')
  await page.goto(`/#/preview/scan/${chronicle.id}?page=5e3a0000-0000-4000-8000-0000000d1f01`)
  await expect(page.getByTestId('scan-overlay')).toBeAttached()
  await page.getByTestId('scan-viewport').focus()
  for (let i = 0; i < 3; i++) await page.keyboard.press('ArrowDown')
  await expect(page.locator('polygon.scan-line--active')).toHaveCount(1)
  await save(page, testInfo, 'scan-viewer')
  await page.keyboard.press('+')
  await page.keyboard.press('+')
  await page.waitForFunction(() => {
    const el = document.querySelector('[data-testid="scan-stage"]')
    return !!el && el.getAnimations().length === 0
  })
  await save(page, testInfo, 'scan-viewer-zoomed')
})

test('public document', async ({ page }, testInfo) => {
  // The public document view (#545): a deep-linked word of the gazette, exact on its scan, the
  // metadata in the sidebar; on a phone the text, then the scan.
  const gazette = fixture.document('gazette')
  const passage = fixture.chunk('gazette_1')
  const word = passage.text.indexOf('hostila')
  await page.goto(`/#/documents/${gazette.id}?chunk=${passage.id}&start=${word}&end=${word + 7}&from=search`)
  await page.reload() // a fresh page
  await expect(page.locator('.is-active-passage')).toHaveText('hostila')
  if (testInfo.project.name !== 'phone') {
    await expect(page.locator('polygon.scan-highlight')).toHaveCount(1)
    await page.getByRole('listitem', { name: 'Document' }).click()
    await expectRightSidebarIn(page)
  }
  await expectSidebarsOpen(page, testInfo)
  await save(page, testInfo, 'public-document')
  if (testInfo.project.name === 'phone') {
    await page.getByTestId('workspace-mode').getByRole('button', { name: 'Scan', exact: true }).click()
    await expect(page.locator('polygon.scan-highlight')).toHaveCount(1)
    await save(page, testInfo, 'public-document-scan')
  }
})

test('collection document with its scan', async ({ page }, testInfo) => {
  // The collection's document view (#545): annotations and tools as before, the scan beside the
  // text, a scan line's text marked.
  await ensureLoggedIn(page, 'owner')
  await page.reload()
  const collection = fixture.collection('chronicles')
  const chronicle = fixture.document('chronicle')
  await page.goto(`/#/collections/${collection.id}/documents/${chronicle.id}/v1?page=5e3a0000-0000-4000-8000-0000000d1f01`)
  await expect(page.locator('.chunk-annotator').first()).toBeVisible()
  // With both sidebars open (narrow) and on a phone the workspace has room for one view only.
  if (testInfo.project.name === 'wide') {
    const line = (await page.locator('polygon.scan-line[data-line-id="r002-l002"]').boundingBox())!
    await page.mouse.click(line.x + line.width / 2, line.y + line.height / 2)
    await expect(page.locator('.is-active-passage').first()).toBeVisible()
  }
  await expectSidebarsOpen(page, testInfo)
  await save(page, testInfo, 'collection-document-scan')
  if (testInfo.project.name === 'narrow') {
    await page.getByTestId('workspace-mode').getByRole('button', { name: 'Scan', exact: true }).click()
    await expect(page.getByTestId('scan-overlay')).toBeAttached()
    await save(page, testInfo, 'collection-document-scan-only')
  }
})

test('explore visualizations', async ({ page }, testInfo) => {
  // #618: the Visualizations view of filters without a text query (no right sidebar panel here).
  await page.goto('/#/search?year_max=1950&chunk_languages=ces&view=visualizations')
  await expect(page.getByTestId('charts-total')).toHaveText('2')
  await expect(page.getByTestId('corpus-years').locator('svg').first()).toBeVisible()
  await expect(page.getByTestId('corpus-languages').locator('svg').first()).toBeVisible()
  await save(page, testInfo, 'explore-visualizations')
  await page.screenshot({ path: `${testInfo.project.outputDir}/ui-capture/explore-visualizations-full-${testInfo.project.name}.png`, fullPage: true })
})

test('explore visualizations of a text query, a chart filter and a data table (#620)', async ({ page }, testInfo) => {
  await page.goto('/#/search?q=Lhota&view=visualizations')
  await expect(page.getByTestId('charts-total')).toHaveText('7')
  await expect(page.getByTestId('results-years').locator('svg').first()).toBeVisible()
  await expect(page.getByTestId('results-languages').locator('svg').first()).toBeVisible()
  await save(page, testInfo, 'explore-ranked-passages')
  await page.screenshot({ path: `${testInfo.project.outputDir}/ui-capture/explore-ranked-passages-full-${testInfo.project.name}.png`, fullPage: true })

  // A clicked 1851 bar: the year filter applied, a new search and its counts.
  await page.getByTestId('results-years').locator('[aria-roledescription="bar"][aria-label*="Click to filter by 1851"]').first().click()
  await expect(page.getByTestId('charts-total')).toHaveText('3')
  await save(page, testInfo, 'explore-ranked-filtered')

  // The language data table opened: exact counts and the bars' filters for the keyboard.
  await page.getByTestId('results-languages-table').getByText(/^Show data table/).click()
  await expect(page.getByTestId('results-languages-table').locator('.q-expansion-item__content')).not.toHaveAttribute('style', /height/)
  await page.getByTestId('results-languages-filter-ces').scrollIntoViewIfNeeded()
  await save(page, testInfo, 'explore-ranked-table')

  // A bounded ranking of documents.
  await page.route('**/api/search/documents', async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    await route.fulfill({ response, json: { ...body, ranked: body.ranked.slice(0, 2), bounded: true, total_count: null } })
  })
  await page.goto('/#/search?q=Lhota&mode=documents&view=visualizations')
  await expect(page.getByTestId('charts-ranking')).toContainText('Bounded')
  await expect(page.getByTestId('results-years').locator('svg').first()).toBeVisible()
  await save(page, testInfo, 'explore-ranked-documents-bounded')
})
