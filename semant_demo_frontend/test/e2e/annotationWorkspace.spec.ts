import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

import { apiToken, deleteAddedSpans, ensureLoggedIn, fixture, sidebarPanelButton, useViewport } from './support'

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
  expect(new Set(keys.map(k => Math.round(k.left))).size, 'annotations start in one column').toBe(1)
  expect(Math.max(...keys.map(k => k.height)), 'every row is one line').toBeLessThan(40)
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
  await expect(sidebarPanelButton(page, 'Document')).toHaveCount(0)

  // Clicking a row opens it in the shared sidebar without checking it.
  await row(page, 'Jan Novák').click()
  await expect(page.getByTestId('right-sidebar-title')).toHaveText('Document')
  await expect(panel(page).getByTestId('chunk-context-mark')).toHaveText('Jan Novák')
  await expect(panel(page).getByTestId('chunk-context-header')).toContainText(fixture.document('chronicle').properties.title)
  await expect(panel(page).getByTestId('annotation-context-text')).toHaveText('Jan Novák')
  await expect(row(page, 'Jan Novák')).toHaveAttribute('aria-selected', 'false')
  await expect(row(page, 'Jan Novák')).toHaveAttribute('aria-current', 'true')

  // Keyboard: arrows move, Space checks, Enter opens.
  await row(page, 'Jan Novák').focus()
  await page.keyboard.press('ArrowDown')
  const keys = await rows(page).locator('.kwic__key').allInnerTexts()
  const next = rows(page).nth(keys.indexOf('Jan Novák') + 1)
  await expect(next).toBeFocused()
  await page.keyboard.press('Space')
  await expect(page.getByTestId('concordance-selected')).toHaveText('2 selected')
  await page.keyboard.press('Enter')
  await expect(next).toHaveAttribute('aria-current', 'true')
  await expect(panel(page).getByTestId('chunk-context-mark')).toHaveText(await next.locator('.kwic__key').innerText())
})

test('filters, selection and the open row survive a visit to the document', async ({ page }) => {
  await useViewport(page, 'narrow')
  await openWorkspace(page)
  await page.getByLabel('Annotated text').fill('nová')
  await expect(rows(page)).toHaveCount(1)
  await row(page, 'Jan Novák').getByRole('checkbox').click()
  await row(page, 'Jan Novák').click()

  await panel(page).getByRole('link', { name: 'Open in document' }).click()
  await expect(page.getByText('Document detail')).toBeVisible()
  await expect(page.locator('.text-segment.is-tagged', { hasText: 'Jan Novák' }).first()).toBeVisible()

  await page.getByRole('link', { name: 'Back to annotations' }).click()
  await expect(page.getByLabel('Annotated text')).toHaveValue('nová')
  await expect(rows(page)).toHaveCount(1)
  await expect(page.getByTestId('concordance-selected')).toHaveText('1 selected')
  await expect(row(page, 'Jan Novák')).toHaveAttribute('aria-current', 'true')
})

test('a long cross-chunk annotation is elided in its row and complete in the sidebar', async ({ page, request }) => {
  const first = fixture.chunk('chronicle_1').text
  const second = fixture.chunk('chronicle_2').text
  await createSpan(request, 'chronicle_1', 10, first.length + 30)
  await useViewport(page, 'narrow')
  await openWorkspace(page)
  const long = row(page, first.slice(10, 40))

  const key = long.locator('.kwic__key')
  expect(await key.evaluate(e => e.scrollWidth > e.clientWidth), 'the key is elided').toBe(true)
  await expect(key).toHaveText(first.slice(10) + second.slice(0, 30))
  const box = await long.boundingBox()
  expect(box?.height).toBeLessThan(40)

  await long.click()
  const marks = panel(page).getByTestId('chunk-context-mark')
  await expect(marks).toHaveText([first.slice(10), second.slice(0, 30)])
  await expect(panel(page).getByTestId('annotation-context-text')).toHaveText(first.slice(10) + second.slice(0, 30))
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
  await panel(page).getByRole('link', { name: 'Open in document' }).click()
  await expect(page.getByText('Document detail')).toBeVisible()
  // The linked proposal is marked although AI assist (which shows proposals) is not open.
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
    await panel(page).getByRole('link', { name: 'Open in document' }).click()
    await expect(page.getByText('Document detail')).toBeVisible()
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
    await expect(page.getByTestId('review-report')).toContainText('Rejected 2 of 2.')
    // Rejected annotations leave the default filters but stay selected, and the bar says so.
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
    const next = rows(page).nth((await rows(page).locator('.kwic__key').allInnerTexts()).indexOf('Lhoty') + 1)
    await review.getByRole('button', { name: 'Approve' }).click()
    await expect(row(page, 'Lhoty')).toContainText('Confirmed')
    // Approving moves on to the next row.
    await expect(next).toHaveAttribute('aria-current', 'true')

    await row(page, first.slice(0, 4)).click()
    await review.getByRole('button', { name: 'Delete…' }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click()
    await expect(row(page, first.slice(0, 4))).toHaveCount(1)
    await review.getByRole('button', { name: 'Delete…' }).click()
    await expect(page.getByRole('dialog')).toContainText('cannot be restored')
    await page.getByRole('dialog').getByRole('button', { name: 'Delete 1' }).click()
    await expect(page.getByTestId('review-report')).toContainText('Deleted 1 of 1.')
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
    await expect(context.getByTestId('provenance-reviewed')).toContainText('Approved by')
    await expect(row(page, 'Lhoty')).toContainText('Confirmed')

    // Rejecting the version shown now is the user's explicit choice.
    await conflict.getByRole('button', { name: 'Apply to current version' }).click()
    await expect(page.getByTestId('review-report')).toContainText('Rejected 1 of 1.')
    await expect(row(page, 'Lhoty')).toHaveCount(0) // rejected: out of the default filters
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
    await expect(conflict).toContainText('It is no longer on this page.')
    await expect(row(page, 'Lhoty')).toHaveCount(0)
    await expect(context.getByTestId('annotation-context-gone')).toHaveCount(0)

    // Reviewing an annotation the page does not show asks first, as for hidden selected ones.
    await conflict.getByRole('button', { name: 'Apply to current version' }).click()
    await expect(page.getByRole('dialog')).toContainText('not on this page')
    await page.getByRole('dialog').getByRole('button', { name: 'Reject 1' }).click()
    await expect(page.getByTestId('review-report')).toContainText('Rejected 1 of 1.')
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
    await expect(report).toContainText('Rejected 1 of 2.')
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
