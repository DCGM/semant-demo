import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

import { apiToken, deleteAddedAttributes, ensureLoggedIn, fixture, useViewport } from './support'

// Assigning attribute values in the annotation workspace (#331, ADR 0011): an optional column
// shows one attribute's values and assigns them on a row, the sidebar edits every attribute of
// the open annotation, a selection is assigned in one batch reported per annotation (only
// confirmed annotations of an applicable tag take values; one changed meanwhile is not
// overwritten), and the attribute filters match exact values and "not assigned". A single-valued
// attribute's picker closes once the choice is saved; values kept after a retag to a tag the
// attribute does not apply to are greyed, marked and cleared like any others (#530 review).

const chronicles = fixture.collection('chronicles')
const base = `/api/user_collections/${chronicles.id}`
const rows = (page: Page) => page.getByTestId('kwic-row')
const row = (page: Page, text: string) => rows(page).filter({ has: page.locator('.kwic__key', { hasText: text }) })
const cell = (page: Page, text: string) => row(page, text).getByTestId('kwic-attribute')
const picker = (page: Page) => page.getByTestId('attribute-value-picker')
const dialog = (page: Page) => page.getByRole('dialog')

async function openWorkspace (page: Page, userKey = 'owner') {
  await ensureLoggedIn(page, userKey)
  await page.goto(`/#/collections/${chronicles.id}/annotations`)
  await expect(page.getByTestId('concordance-range')).toContainText('matching annotations')
}

/** "Role", several values, for the person tag only (Jan Novák; not the place Brně). */
async function createRole (request: APIRequestContext) {
  const created = await request.post(`${base}/attributes`, {
    headers: { Authorization: `Bearer ${await apiToken(request, 'owner')}` },
    data: {
      name: 'Role',
      cardinality: 'multi',
      all_tags: false,
      tag_ids: [fixture.tag('person').id],
      values: [{ label: 'statesman' }, { label: 'chronicler' }, { label: 'Unknown', kind: 'unknown' }]
    }
  })
  expect(created.ok()).toBe(true)
  return await created.json() as { id: string, values: { id: string, label: string }[] }
}

async function choose (page: Page, testid: string, option: string) {
  await page.getByTestId(testid).click()
  await page.getByRole('option', { name: option, exact: true }).click()
}

/** Closes the open value picker and waits until it has faded out, so the next picker opened is
 * the only one on the page. */
async function closePicker (page: Page) {
  await page.keyboard.press('Escape')
  await expect(picker(page)).toHaveCount(0)
}

/** Toggles one option of a multiple select and closes its menu. */
async function toggleOption (page: Page, testid: string, option: string) {
  await choose(page, testid, option)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('listbox')).toHaveCount(0)
}

test.afterEach(async ({ request }) => {
  await deleteAddedAttributes(request, 'owner', 'chronicles')
})

test('a row is classified in the attribute column and in the sidebar, and filtered by it', async ({ page, request }) => {
  await createRole(request)
  await useViewport(page, 'wide')
  await openWorkspace(page)

  // No column until one is chosen.
  await expect(page.getByTestId('kwic-attribute')).toHaveCount(0)
  await choose(page, 'concordance-show-attribute', 'Role')
  await expect(page.getByTestId('kwic-attribute')).toHaveCount(4)
  // Proposals and a tag the attribute does not apply to cannot take values.
  await expect(cell(page, 'Lhoty').getByTestId('kwic-attribute-edit')).toHaveCount(0)
  await expect(cell(page, 'Brně').getByTestId('kwic-attribute-edit')).toHaveCount(0)

  await cell(page, 'Jan Novák').getByTestId('kwic-attribute-edit').click()
  await picker(page).getByText('statesman', { exact: true }).click()
  await expect(cell(page, 'Jan Novák')).toContainText('statesman')
  await picker(page).getByText('chronicler', { exact: true }).click()
  await expect(cell(page, 'Jan Novák')).toContainText('chronicler')
  // Unknown stands alone: it replaces the values.
  await picker(page).getByText('Unknown', { exact: true }).click()
  await expect(cell(page, 'Jan Novák').getByTestId('attribute-chips')).toHaveText('Unknown')
  await closePicker(page)

  // The sidebar shows the same values and changes them.
  await row(page, 'Jan Novák').click()
  const attributes = page.getByTestId('annotation-attributes')
  await expect(attributes).toContainText('Role')
  await expect(attributes.getByTestId('attribute-chips')).toHaveText('Unknown')
  await attributes.getByTestId('annotation-attribute-edit').click()
  await picker(page).getByText('statesman', { exact: true }).click()
  await expect(attributes.getByTestId('attribute-chips')).toHaveText('statesman')
  await expect(cell(page, 'Jan Novák').getByTestId('attribute-chips')).toHaveText('statesman')
  await closePicker(page)

  // Exact filters: the value, and "not assigned".
  await toggleOption(page, 'concordance-attributes', 'Role: statesman')
  await expect(rows(page)).toHaveCount(1)
  await expect(row(page, 'Jan Novák')).toHaveCount(1)
  await toggleOption(page, 'concordance-attributes', 'Role: statesman')
  await expect(rows(page)).toHaveCount(4)
  await toggleOption(page, 'concordance-attributes', 'Role: not assigned')
  await expect(rows(page)).toHaveCount(3)
  await expect(row(page, 'Jan Novák')).toHaveCount(0)
})

test('a selection is assigned in one batch, reported per annotation, without overwriting a newer change', async ({ page, request }) => {
  const role = await createRole(request)
  const novak = fixture.span('novak_manual').id
  await useViewport(page, 'wide')
  await openWorkspace(page)
  await choose(page, 'concordance-show-attribute', 'Role')
  await page.getByTestId('select-all-matches').click()
  await expect(page.getByTestId('concordance-selected')).toHaveText('4 selected')

  // Someone else classifies Jan Novák after it was selected.
  const headers = { Authorization: `Bearer ${await apiToken(request, 'annotator')}` }
  const listed = await request.get(`${base}/annotations`, { headers, params: { annotation_id: novak } })
  const version = (await listed.json()).rows[0].attributeVersion as number
  const theirs = await request.post(`${base}/annotations/attributes/assign`, {
    headers,
    data: { attribute_id: role.id, annotation_ids: [novak], expected_versions: { [novak]: version }, mode: 'add', value_ids: [role.values[1]!.id] }
  })
  expect((await theirs.json()).outcome).toBe('complete')

  await page.getByTestId('assign-attribute').click()
  await expect(dialog(page).getByTestId('assign-target')).toContainText('To 4 selected annotations')
  await choose(page, 'assign-dialog-attribute', 'Role (several values)')
  await dialog(page).getByRole('checkbox', { name: 'statesman' }).click()
  await expect(dialog(page).getByTestId('assign-summary')).toContainText('Add "statesman" to "Role" of 4 annotations.')
  await dialog(page).getByRole('button', { name: 'Add to 4' }).click()
  await expect(dialog(page)).toHaveCount(0)

  const report = page.getByTestId('assign-report')
  // A headline, then each count on its own line next to its reason.
  await expect(report.getByTestId('assign-report-title')).toHaveText('"Role": saved 0 of 4 annotations')
  await expect(report.getByTestId('assign-report-lines').getByRole('listitem')).toHaveText([
    /^1\s*not saved\s*Changed by someone else since you selected them\.$/,
    /^2\s*not changed\s*Only confirmed annotations take values\.$/,
    /^1\s*not changed\s*The attribute does not apply to their tag\.$/
  ])
  // The row shows the other person's value, as the server answered.
  await expect(cell(page, 'Jan Novák').getByTestId('attribute-chips')).toHaveText('chronicler')

  // The changed one is selected again at its current version and assigned.
  await report.getByTestId('assign-show-changed').click()
  await expect(page.getByTestId('concordance-selected')).toHaveText('1 selected')
  await page.getByTestId('assign-attribute').click()
  await choose(page, 'assign-dialog-attribute', 'Role (several values)')
  await dialog(page).getByRole('checkbox', { name: 'statesman' }).click()
  await dialog(page).getByRole('button', { name: 'Add to 1' }).click()
  await expect(page.getByTestId('assign-report-title')).toHaveText('"Role": saved 1 of 1 annotation')
  await expect(page.getByTestId('assign-report-lines')).toHaveCount(0)
  await expect(cell(page, 'Jan Novák').getByTestId('attribute-chips')).toHaveText('statesmanchronicler')
})

test('a single-valued choice closes its picker once saved, in the column and in the sidebar', async ({ page, request }) => {
  const created = await request.post(`${base}/attributes`, {
    headers: { Authorization: `Bearer ${await apiToken(request, 'owner')}` },
    data: { name: 'Place type', cardinality: 'single', all_tags: true, values: [{ label: 'town' }, { label: 'village' }] }
  })
  expect(created.ok()).toBe(true)
  await useViewport(page, 'wide')
  await openWorkspace(page)
  await choose(page, 'concordance-show-attribute', 'Place type')

  await cell(page, 'Brně').getByTestId('kwic-attribute-edit').click()
  await picker(page).getByText('town', { exact: true }).click()
  await expect(cell(page, 'Brně').getByTestId('attribute-chips')).toHaveText('town')
  await expect(picker(page)).toHaveCount(0)

  await row(page, 'Brně').click()
  const attributes = page.getByTestId('annotation-attributes')
  await attributes.getByTestId('annotation-attribute-edit').click()
  await picker(page).getByText('village', { exact: true }).click()
  await expect(attributes.getByTestId('attribute-chips')).toHaveText('village')
  await expect(picker(page)).toHaveCount(0)
  // The keyboard path stays the sidebar: the column cell is not a tab stop.
  await expect(cell(page, 'Brně').getByTestId('kwic-attribute-edit')).toHaveAttribute('tabindex', '-1')
})

test('values kept after a retag are greyed and marked, and a batch Clear removes them', async ({ page, request }) => {
  const role = await createRole(request)
  const headers = { Authorization: `Bearer ${await apiToken(request, 'owner')}` }
  const novak = fixture.span('novak_manual').id
  const listed = await request.get(`${base}/annotations`, { headers, params: { annotation_id: novak } })
  const version = (await listed.json()).rows[0].attributeVersion as number
  const assigned = await request.post(`${base}/annotations/attributes/assign`, {
    headers,
    data: { attribute_id: role.id, annotation_ids: [novak], expected_versions: { [novak]: version }, mode: 'add', value_ids: [role.values[0]!.id] }
  })
  expect((await assigned.json()).outcome).toBe('complete')
  const retag = (tag: string) => request.patch(`/api/tag_spans/${novak}`, {
    headers, params: { collection_id: chronicles.id }, data: { tagId: fixture.tag(tag).id }
  })
  expect((await retag('place')).ok()).toBe(true)
  try {
    await useViewport(page, 'wide')
    await openWorkspace(page)
    await choose(page, 'concordance-show-attribute', 'Role')
    const kept = cell(page, 'Jan Novák')
    await expect(kept).toContainText('statesman')
    await expect(kept.getByTestId('attribute-chips-inapplicable')).toBeVisible()
    await expect(kept.getByTestId('kwic-attribute-edit')).toHaveCount(0)

    await row(page, 'Jan Novák').getByRole('checkbox').click()
    await page.getByTestId('assign-attribute').click()
    await choose(page, 'assign-dialog-attribute', 'Role (several values)')
    await dialog(page).getByRole('button', { name: 'Clear', exact: true }).click()
    await dialog(page).getByRole('button', { name: 'Clear on 1' }).click()
    await expect(page.getByTestId('assign-report-title')).toHaveText('"Role": saved 1 of 1 annotation')
    await expect(kept.getByTestId('attribute-chips-inapplicable')).toHaveCount(0)
    await expect(kept).toContainText('–')
  } finally {
    expect((await retag('person')).ok()).toBe(true)
  }
})
