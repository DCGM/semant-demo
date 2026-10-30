import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

import { apiToken, deleteAddedAttributes, deleteAddedTags, ensureLoggedIn, fixture, useViewport } from './support'

// Attribute definitions of a collection (#331, ADR 0011), in the Attributes part of the Tags &
// attributes tab (#506): cards stay compact with ~100 values, the Edit dialog manages values,
// each saved at once, Unknown / Not applicable are fixed and only retired / restored, the UI
// offers Retire / Restore and never Delete, search highlights matches and says what Show
// retired hides, narrowing the tags of a used attribute is refused with the count, and the
// Tags part shows each tag's attributes.

const chronicles = fixture.collection('chronicles')
const base = `/api/user_collections/${chronicles.id}`
const card = (page: Page, name: string) =>
  page.getByTestId('attribute').filter({ has: page.getByTestId('attribute-name').getByText(name, { exact: true }) })
const chips = (page: Page, attribute: string) => card(page, attribute).getByTestId('attribute-value-label')
const chip = (page: Page, attribute: string, label: string) =>
  card(page, attribute).getByTestId('attribute-value').filter({ has: page.getByText(label, { exact: true }) })
const dialog = (page: Page) => page.getByRole('dialog')
const valueRow = (page: Page, label: string) =>
  dialog(page).getByTestId('attribute-dialog-value-row').filter({ has: page.getByText(label, { exact: true }) })

async function openAttributes (page: Page, userKey = 'owner') {
  await ensureLoggedIn(page, userKey)
  await page.goto(`/#/collections/${chronicles.id}/attributes`)
  await expect(page.getByTestId('attributes-title')).toHaveText(/Attributes \(\d+\)/)
}

const headersOf = async (request: APIRequestContext) => ({ Authorization: `Bearer ${await apiToken(request, 'owner')}` })

type Listed = { id: string, name: string, values: { id: string, label: string, kind: string, retired: boolean }[] }

async function createAttribute (request: APIRequestContext, data: Record<string, unknown>): Promise<Listed> {
  const created = await request.post(`${base}/attributes`, { headers: await headersOf(request), data })
  expect(created.ok()).toBe(true)
  return await created.json() as Listed
}

async function listed (request: APIRequestContext, name: string): Promise<Listed> {
  const answer = await request.get(`${base}/attributes`, { headers: await headersOf(request) })
  return (await answer.json() as Listed[]).find(a => a.name === name)!
}

/** Creates "Speaker" (person tag) with one value and gives it to the approved Jan Novák. */
async function speakerOnNovak (request: APIRequestContext) {
  const headers = await headersOf(request)
  const attribute = await createAttribute(request, {
    name: 'Speaker', cardinality: 'single', tag_ids: [fixture.tag('person').id], values: [{ label: 'politician' }]
  })
  const novak = fixture.span('novak_manual').id
  const rows = await request.get(`${base}/annotations`, { headers, params: { annotation_id: novak } })
  const version = (await rows.json()).rows[0].attributeVersion
  const assigned = await request.post(`${base}/annotations/attributes/assign`, {
    headers,
    data: {
      attribute_id: attribute.id,
      annotation_ids: [novak],
      expected_versions: { [novak]: version },
      mode: 'replace',
      value_ids: [attribute.values[0]!.id]
    }
  })
  expect((await assigned.json()).outcome).toBe('complete')
}

/** "Topic" with 100 values (one retired) and a long description, and a retired "Election year". */
async function largeTopic (request: APIRequestContext) {
  const values = [
    { label: 'elections' },
    ...Array.from({ length: 98 }, (_, i) => ({ label: `topic ${String(i).padStart(3, '0')}` })),
    { label: 'electoral law' }
  ]
  const topic = await createAttribute(request, {
    name: 'Topic',
    description: Array.from({ length: 12 }, (_, i) => `Line ${i + 1} of what a topic records, and how to choose one.`).join('\n'),
    cardinality: 'multi',
    values
  })
  const law = topic.values.find(v => v.label === 'electoral law')!
  const headers = await headersOf(request)
  expect((await request.patch(`${base}/attributes/${topic.id}/values/${law.id}`, { headers, data: { retired: true } })).ok()).toBe(true)
  const year = await createAttribute(request, { name: 'Election year', values: [{ label: '1920' }] })
  expect((await request.patch(`${base}/attributes/${year.id}`, { headers, data: { retired: true } })).ok()).toBe(true)
}

test.afterEach(async ({ request }) => {
  await deleteAddedAttributes(request, 'owner', 'chronicles')
  await deleteAddedTags(request, 'owner', 'chronicles')
})

test('the owner defines an attribute and manages its values in Edit, each saved at once', async ({ page, request }) => {
  await useViewport(page, 'wide')
  // Attributes are a part of the Tags & attributes tab, which stays active on either part.
  await ensureLoggedIn(page, 'owner')
  await page.goto(`/#/collections/${chronicles.id}/tags`)
  await page.getByRole('tab', { name: 'Attributes', exact: true }).click()
  await expect(page).toHaveURL(/\/attributes$/)
  await expect(page.getByRole('tab', { name: 'Tags & attributes' })).toHaveClass(/q-tab--active/)
  await expect(page.getByTestId('attributes-empty')).toContainText('No attributes yet')

  await page.getByTestId('attribute-create').click()
  await dialog(page).getByLabel('Name').fill('Speaker type')
  await dialog(page).getByLabel('Description').fill('Who says the quoted words.')
  await dialog(page).getByRole('checkbox', { name: 'Allow multiple values per annotation' }).click()
  await expect(page.getByTestId('attribute-multiple-warning')).toContainText('cannot be reversed')
  await dialog(page).getByRole('checkbox', { name: 'Allow multiple values per annotation' }).click()
  await dialog(page).getByRole('radio', { name: 'Selected tags' }).click()
  await dialog(page).getByRole('button', { name: 'Create' }).click()
  await expect(dialog(page)).toContainText('Choose at least one tag, or choose All tags')
  await dialog(page).getByLabel('Tags', { exact: true }).click()
  await page.getByRole('option', { name: fixture.tag('person').name }).click()
  await page.keyboard.press('Escape')
  await dialog(page).getByLabel('Value 1', { exact: true }).fill('politician')
  await dialog(page).getByRole('button', { name: 'Add value', exact: true }).click()
  await dialog(page).getByLabel('Value 2', { exact: true }).fill('journalist')
  await dialog(page).getByRole('checkbox', { name: 'Allow Unknown' }).click()
  await dialog(page).getByRole('button', { name: 'Create' }).click()

  await expect(card(page, 'Speaker type').getByTestId('attribute-cardinality')).toHaveText('One value per annotation')
  await expect(card(page, 'Speaker type').getByTestId('attribute-tags')).toHaveText(fixture.tag('person').name)
  await expect(card(page, 'Speaker type').getByTestId('attribute-description')).toContainText('Who says the quoted words.')
  await expect(chips(page, 'Speaker type')).toHaveText(['politician', 'journalist', 'Unknown'])
  // No value can be deleted or edited from the card; the attribute is edited or retired.
  const actions = card(page, 'Speaker type').getByRole('button')
  await expect(actions).toHaveCount(2)
  await expect(actions.first()).toHaveAccessibleName('Edit Speaker type')
  await expect(actions.last()).toHaveAccessibleName('Retire Speaker type')
  await expect(page.getByRole('button', { name: /^Delete/ })).toHaveCount(0)

  // A second attribute of the same name is refused; the dialog keeps what was typed.
  await page.getByTestId('attribute-create').click()
  await dialog(page).getByLabel('Name').fill('speaker TYPE')
  await dialog(page).getByRole('button', { name: 'Create' }).click()
  await expect(page.getByTestId('attribute-dialog-error')).toContainText('already exists')
  await expect(dialog(page).getByLabel('Name')).toHaveValue('speaker TYPE')
  await dialog(page).getByRole('button', { name: 'Cancel', exact: true }).click()
  await page.getByRole('button', { name: 'Yes' }).click()

  const unknownId = (await listed(request, 'Speaker type')).values.find(v => v.kind === 'unknown')!.id
  await page.getByRole('button', { name: 'Edit Speaker type' }).click()
  await expect(dialog(page).getByRole('checkbox', { name: 'Allow multiple values per annotation' })).toBeDisabled()
  await expect(page.getByTestId('attribute-values-immediate')).toContainText('saved immediately')
  // Value changes are saved at once, behind the dialog.
  await dialog(page).getByRole('checkbox', { name: 'Allow Not applicable' }).click()
  await expect(chips(page, 'Speaker type')).toHaveText(['politician', 'journalist', 'Unknown', 'Not applicable'])
  await dialog(page).getByRole('checkbox', { name: 'Allow Unknown' }).click()
  await expect(chip(page, 'Speaker type', 'Unknown')).toContainText('Retired')
  await valueRow(page, 'journalist').getByRole('button', { name: 'Retire journalist' }).click()
  await expect(valueRow(page, 'journalist')).toContainText('Retired')
  await dialog(page).getByRole('button', { name: 'Edit politician' }).click()
  await dialog(page).last().getByLabel('Description').fill('Holds or seeks public office.')
  await dialog(page).last().getByLabel('Example 1', { exact: true }).fill('a member of parliament')
  await dialog(page).last().getByRole('button', { name: 'Save' }).click()
  await expect(valueRow(page, 'politician')).toContainText('Holds or seeks public office. · e.g. a member of parliament')
  await dialog(page).getByRole('button', { name: 'Add value', exact: true }).click()
  await dialog(page).last().getByLabel('Label').fill('spokesperson')
  await dialog(page).last().getByRole('button', { name: 'Add', exact: true }).click()
  await expect(valueRow(page, 'spokesperson')).toBeVisible()
  await expect(dialog(page)).toHaveCount(1) // the value dialog has closed
  // Cancel discards the renamed name only: the value changes are already saved.
  await dialog(page).getByLabel('Name').fill('Speaker')
  await dialog(page).getByRole('button', { name: 'Cancel', exact: true }).click()
  await page.getByRole('button', { name: 'Yes' }).click()
  await expect(chips(page, 'Speaker type')).toHaveText(['politician', 'journalist', 'spokesperson', 'Unknown', 'Not applicable'])
  await expect(chip(page, 'Speaker type', 'journalist')).toContainText('Retired')

  // Offering Unknown again restores the same value; nothing creates a second one.
  await page.getByRole('button', { name: 'Edit Speaker type' }).click()
  await dialog(page).getByRole('checkbox', { name: 'Allow Unknown' }).click()
  await expect(dialog(page).getByRole('checkbox', { name: 'Allow Unknown' })).toBeChecked()
  await dialog(page).getByRole('button', { name: 'Save' }).click()
  const unknowns = (await listed(request, 'Speaker type')).values.filter(v => v.kind === 'unknown')
  expect(unknowns.map(v => [v.id, v.retired])).toEqual([[unknownId, false]])

  // Retiring the attribute from its card, and restoring it.
  await page.getByRole('button', { name: 'Retire Speaker type' }).click()
  await expect(card(page, 'Speaker type')).toHaveClass(/attribute--retired/)
  await page.getByRole('button', { name: 'Restore Speaker type' }).click()
  await expect(card(page, 'Speaker type')).not.toHaveClass(/attribute--retired/)

  // The list is what the backend stores.
  await page.reload()
  await expect(chips(page, 'Speaker type')).toHaveText(['politician', 'journalist', 'spokesperson', 'Unknown', 'Not applicable'])
})

for (const viewport of ['wide', 'phone'] as const) {
  test(`~100 values stay bounded and search finds them (${viewport})`, async ({ page, request }) => {
    await largeTopic(request)
    await useViewport(page, viewport)
    await openAttributes(page)
    const topic = card(page, 'Topic')
    const height = async () => (await topic.boundingBox())!.height

    // Two lines of chips and a clamped description, expanding within bounds.
    expect(await height()).toBeLessThan(viewport === 'phone' ? 420 : 300)
    await topic.getByRole('button', { name: /^\+\d+ more$/ }).click()
    await expect(topic.getByRole('button', { name: 'Show less' })).toBeVisible()
    expect(await height()).toBeLessThan(viewport === 'phone' ? 620 : 500)
    await topic.getByRole('button', { name: 'Show less' }).click()
    await topic.getByRole('button', { name: 'Show more' }).click()
    await expect(topic.getByTestId('attribute-description')).toContainText('Line 12')

    // Matches come first and are marked; what Show retired hides is counted, not shown.
    await page.getByTestId('attribute-show-retired').click()
    await page.getByLabel('Search attributes and values').fill('elect')
    await expect(page.getByTestId('attribute')).toHaveCount(1)
    await expect(chips(page, 'Topic').first()).toHaveText('elections')
    await expect(chips(page, 'Topic').first().locator('mark')).toHaveText('elect')
    await expect(chip(page, 'Topic', 'electoral law')).toHaveCount(0)
    await expect(page.getByTestId('attribute-hidden-matches')).toContainText('2 retired matches hidden.')
    await page.getByTestId('attribute-hidden-matches').getByRole('button', { name: 'Show retired' }).click()
    await expect(page.getByTestId('attribute')).toHaveCount(2)
    await expect(chips(page, 'Topic').nth(1)).toHaveText('electoral law')
    await expect(page.getByTestId('attribute-hidden-matches')).toHaveCount(0)
    await page.getByLabel('Search attributes and values').fill('no such thing')
    await expect(page.getByTestId('attributes-empty')).toHaveText('No attributes match.')
    await page.getByLabel('Search attributes and values').fill('')

    // The Edit dialog lists the values in a bounded, searchable list and keeps Save reachable.
    await page.getByRole('button', { name: 'Edit Topic' }).click()
    const list = dialog(page).locator('.attribute-values-editor__list')
    expect((await list.boundingBox())!.height).toBeLessThanOrEqual(321)
    await expect(dialog(page).getByRole('button', { name: 'Save' })).toBeInViewport()
    await dialog(page).getByPlaceholder('Search values').fill('topic 05')
    await expect(dialog(page).getByTestId('attribute-dialog-value-row')).toHaveCount(10)
    await expect(dialog(page)).toContainText('10 of 100 values match.')
    await dialog(page).getByRole('button', { name: 'Cancel', exact: true }).click()
  })
}

test('a shared user sees tag-side attributes, a refused narrowing and frozen fields while saving', async ({ page, request }) => {
  await speakerOnNovak(request)
  await createAttribute(request, { name: 'Mood', values: [{ label: 'calm' }] })
  await useViewport(page, 'phone')
  await ensureLoggedIn(page, 'annotator')

  // The Tags part lists each tag's attributes: those naming it, then those for all tags.
  await page.goto(`/#/collections/${chronicles.id}/tags`)
  const row = (tag: string) => page.locator('tbody tr').filter({ has: page.getByText(tag, { exact: true }) })
  await expect(row(fixture.tag('person').name).getByTestId('tag-attribute')).toHaveText(['Speaker', 'MoodAll tags'])
  await expect(row(fixture.tag('place').name).getByTestId('tag-attribute')).toHaveText(['MoodAll tags'])

  // Narrowing to another tag would leave Jan Novák (a person) with a value that does not apply.
  await openAttributes(page, 'annotator')
  await page.getByRole('button', { name: 'Edit Speaker' }).click()
  await dialog(page).getByLabel('Tags', { exact: true }).click()
  await page.getByRole('option', { name: fixture.tag('place').name }).click()
  await page.getByRole('option', { name: fixture.tag('person').name }).click()
  await page.keyboard.press('Escape')
  await dialog(page).getByRole('button', { name: 'Save' }).click()
  await expect(dialog(page).getByTestId('attribute-scope-section'))
    .toContainText('1 annotations with values of this attribute have a tag outside')
  await expect(page.getByTestId('attribute-dialog-error')).toHaveCount(0)
  await expect(dialog(page).getByRole('button', { name: 'Save' })).toBeInViewport()
  await dialog(page).getByRole('button', { name: 'Cancel', exact: true }).click()
  await page.getByRole('button', { name: 'Yes' }).click()
  await expect(card(page, 'Speaker').getByTestId('attribute-tags')).toHaveText(fixture.tag('person').name)

  // A slow save freezes the fields it sends until it answers.
  let release!: () => void
  const released = new Promise<void>(resolve => { release = resolve })
  await page.route(`**${base}/attributes/*`, async route => {
    if (route.request().method() !== 'PATCH') return await route.fallback()
    await released
    await route.fallback()
  })
  await page.getByRole('button', { name: 'Edit Mood' }).click()
  await dialog(page).getByLabel('Description').fill('How the speaker sounds.')
  await dialog(page).getByRole('button', { name: 'Save' }).click()
  await expect(dialog(page).getByLabel('Description')).toBeDisabled()
  await expect(dialog(page).getByLabel('Name')).toBeDisabled()
  await expect(dialog(page).getByRole('button', { name: 'Retire calm' })).toBeDisabled()
  release()
  await expect(dialog(page)).toHaveCount(0)
  await expect(card(page, 'Mood').getByTestId('attribute-description')).toHaveText('How the speaker sounds.')
})

test('tags that are loading, failed or deleted are never shown as something else', async ({ page, request }) => {
  const headers = await headersOf(request)
  const tag = await request.post('/api/tags', {
    headers,
    params: { collection_id: chronicles.id },
    data: { name: 'Interview', shorthand: 'INT', color: '#888888', pictogram: 'mic', definition: 'An interview.' }
  })
  expect(tag.ok()).toBe(true)
  const tagId = (await tag.json() as { id: string }).id
  await createAttribute(request, { name: 'Mood', cardinality: 'single', tag_ids: [tagId], values: [{ label: 'calm' }] })
  await createAttribute(request, { name: 'Speaker', tag_ids: [fixture.tag('person').id], values: [{ label: 'politician' }] })
  expect((await request.delete(`/api/tags/${tagId}`, { headers })).ok()).toBe(true)
  await useViewport(page, 'wide')

  // While the tags fail to load, no attribute is said to apply to deleted tags only.
  await ensureLoggedIn(page, 'owner')
  await page.route(`**${base}/tags`, route => route.fulfill({ status: 500, body: '{}' }))
  await page.goto(`/#/collections/${chronicles.id}/attributes`)
  await expect(page.getByTestId('attribute-tags-error')).toBeVisible()
  await expect(card(page, 'Speaker').getByTestId('attribute-tags')).toHaveText('Tags could not be loaded')
  await expect(page.getByRole('button', { name: 'Edit Speaker' })).toBeDisabled()
  await page.unroute(`**${base}/tags`)
  await page.getByTestId('attribute-tags-error').getByRole('button', { name: 'Try again' }).click()
  await expect(card(page, 'Speaker').getByTestId('attribute-tags')).toHaveText(fixture.tag('person').name)
  await expect(card(page, 'Mood').getByTestId('attribute-tags')).toHaveText('Only deleted tags')

  // Adding a tag next to the deleted one is refused in the form until the deleted one is removed.
  await page.getByRole('button', { name: 'Edit Mood' }).click()
  await expect(page.getByTestId('attribute-deleted-tag')).toHaveText(/Deleted tag/)
  await dialog(page).getByLabel('Tags', { exact: true }).click()
  await page.getByRole('option', { name: fixture.tag('person').name }).click()
  await page.keyboard.press('Escape')
  await dialog(page).getByRole('button', { name: 'Save' }).click()
  await expect(dialog(page)).toContainText('Remove the deleted tags, or leave the tags unchanged')
  // Removing the deleted tag alone would leave no tag: Selected tags never becomes All tags.
  await page.getByTestId('attribute-deleted-tag').locator('.q-chip__icon--remove').click()
  await dialog(page).getByRole('button', { name: 'Save' }).click()
  await expect(card(page, 'Mood').getByTestId('attribute-tags')).toHaveText(fixture.tag('person').name)
})
