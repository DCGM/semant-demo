import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

import { apiToken, deleteAddedAttributes, deleteAddedTags, ensureLoggedIn, fixture, useViewport } from './support'

// Attribute definitions of a collection (#331, ADR 0011), in the Attributes part of the Tags &
// attributes tab: the owner and shared users create attributes with values, rename and retire
// them; a used value or attribute is not deleted but can be retired, narrowing the tags of a
// used attribute is refused with the count, and a deleted applicable tag is shown as such.

const chronicles = fixture.collection('chronicles')
const base = `/api/user_collections/${chronicles.id}`
const card = (page: Page, name: string) =>
  page.getByTestId('attribute').filter({ has: page.getByTestId('attribute-name').getByText(name, { exact: true }) })
const value = (page: Page, attribute: string, label: string) =>
  card(page, attribute).getByTestId('attribute-value').filter({ has: page.getByText(label, { exact: true }) })

async function openAttributes (page: Page, userKey = 'owner') {
  await ensureLoggedIn(page, userKey)
  await page.goto(`/#/collections/${chronicles.id}/attributes`)
  await expect(page.getByTestId('attributes-title')).toHaveText(/Attributes \(\d+\)/)
}

const headersOf = async (request: APIRequestContext) => ({ Authorization: `Bearer ${await apiToken(request, 'owner')}` })

/** Creates "Speaker" (person tag) with one value and gives it to the approved Jan Novák. */
async function speakerOnNovak (request: APIRequestContext) {
  const headers = await headersOf(request)
  const created = await request.post(`${base}/attributes`, {
    headers,
    data: { name: 'Speaker', cardinality: 'single', tag_ids: [fixture.tag('person').id], values: [{ label: 'politician' }] }
  })
  expect(created.ok()).toBe(true)
  const attribute = await created.json() as { id: string, values: { id: string }[] }
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

test.afterEach(async ({ request }) => {
  await deleteAddedAttributes(request, 'owner', 'chronicles')
  await deleteAddedTags(request, 'owner', 'chronicles')
})

test('the owner defines an attribute with values, renames and retires it', async ({ page }) => {
  await useViewport(page, 'wide')
  // Attributes are a part of the Tags & attributes tab, which stays active on either part.
  await ensureLoggedIn(page, 'owner')
  await page.goto(`/#/collections/${chronicles.id}/tags`)
  await page.getByRole('tab', { name: 'Attributes', exact: true }).click()
  await expect(page).toHaveURL(/\/attributes$/)
  await expect(page.getByRole('tab', { name: 'Tags & attributes' })).toHaveClass(/q-tab--active/)
  await expect(page.getByTestId('attributes-empty')).toContainText('No attributes yet')

  await page.getByTestId('attribute-create').click()
  await page.getByLabel('Name').fill('Speaker type')
  await page.getByLabel('Description').fill('Who says the quoted words.')
  await page.getByRole('radio', { name: 'One value' }).click()
  await page.getByLabel('Applies to tags').click()
  await page.getByRole('option', { name: fixture.tag('person').name }).click()
  await page.keyboard.press('Escape')
  await page.getByLabel('Value 1', { exact: true }).fill('politician')
  await page.getByRole('button', { name: 'Add value', exact: true }).click()
  await page.getByLabel('Value 2', { exact: true }).fill('journalist')
  await page.getByRole('button', { name: 'Add value', exact: true }).click()
  // A row with a special kind but no label is not dropped silently.
  await page.getByTestId('attribute-dialog-value').nth(2).getByLabel('Kind').click()
  await page.getByRole('option', { name: 'Unknown' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Create' }).click()
  await expect(page.getByTestId('attribute-dialog-value').nth(2)).toContainText('Label is required')
  await page.getByLabel('Value 3', { exact: true }).fill('not known')
  await page.getByRole('dialog').getByRole('button', { name: 'Create' }).click()

  await expect(card(page, 'Speaker type')).toContainText(`One value per annotation · tags ${fixture.tag('person').name}`)
  await expect(card(page, 'Speaker type')).toContainText('Who says the quoted words.')
  await expect(card(page, 'Speaker type').getByTestId('attribute-value-label')).toHaveText(['politician', 'journalist', 'not known'])
  await expect(value(page, 'Speaker type', 'not known')).toContainText('Unknown')

  // A second attribute of the same name is refused; the dialog keeps what was typed.
  await page.getByTestId('attribute-create').click()
  await page.getByLabel('Name').fill('speaker TYPE')
  await page.getByRole('dialog').getByRole('button', { name: 'Create' }).click()
  await expect(page.getByTestId('attribute-dialog-error')).toContainText('already exists')
  await expect(page.getByLabel('Name')).toHaveValue('speaker TYPE')
  await page.getByRole('button', { name: 'Cancel' }).click()
  await page.getByRole('button', { name: 'Yes' }).click()

  // Renaming keeps the values; the cardinality is fixed.
  await page.getByRole('button', { name: 'Edit Speaker type' }).click()
  await expect(page.getByTestId('attribute-cardinality')).toContainText('cannot be changed')
  await page.getByLabel('Name').fill('Speaker')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(card(page, 'Speaker').getByTestId('attribute-value-label')).toHaveText(['politician', 'journalist', 'not known'])

  // A value added later, and a value's description and examples edited.
  await page.getByRole('button', { name: 'Add a value to Speaker' }).click()
  await page.getByRole('dialog').getByLabel('Label').fill('spokesperson')
  await page.getByRole('dialog').getByLabel('Kind').click()
  await expect(page.getByRole('option', { name: 'Unknown' })).toHaveAttribute('aria-disabled', 'true')
  await page.getByRole('option', { name: 'Value' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Add', exact: true }).click()
  await expect(card(page, 'Speaker').getByTestId('attribute-value-label')).toHaveText(['politician', 'journalist', 'not known', 'spokesperson'])
  await page.getByRole('button', { name: 'Edit politician' }).click()
  await page.getByRole('dialog').getByLabel('Description').fill('Holds or seeks public office.')
  await page.getByRole('dialog').getByLabel('Example 1', { exact: true }).fill('a member of parliament')
  await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click()
  await expect(value(page, 'Speaker', 'politician')).toContainText('Holds or seeks public office. · e.g. a member of parliament')

  // Retiring a value keeps it listed until retired ones are hidden; restoring brings it back.
  await page.getByRole('button', { name: 'Retire journalist' }).click()
  await expect(value(page, 'Speaker', 'journalist')).toContainText('Retired')
  await page.getByTestId('attribute-show-retired').click()
  await expect(value(page, 'Speaker', 'journalist')).toHaveCount(0)
  await page.getByTestId('attribute-show-retired').click()
  await page.getByRole('button', { name: 'Restore journalist' }).click()
  await expect(value(page, 'Speaker', 'journalist')).not.toContainText('Retired')

  // An unused value is deleted.
  await page.getByRole('button', { name: 'Delete journalist' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Delete' }).click()
  await expect(card(page, 'Speaker').getByTestId('attribute-value-label')).toHaveText(['politician', 'not known', 'spokesperson'])

  // The list is what the backend stores.
  await page.reload()
  await expect(card(page, 'Speaker').getByTestId('attribute-value-label')).toHaveText(['politician', 'not known', 'spokesperson'])
  await expect(value(page, 'Speaker', 'politician')).toContainText('a member of parliament')
})

test('a shared user cannot delete a used value or narrow its tags, and retires it instead', async ({ page, request }) => {
  await speakerOnNovak(request)
  await useViewport(page, 'phone')
  await openAttributes(page, 'annotator')
  await expect(card(page, 'Speaker')).toBeVisible()

  await page.getByRole('button', { name: 'Delete politician' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Delete' }).click()
  await expect(page.getByRole('dialog').filter({ hasText: 'Still in use' }))
    .toContainText('1 annotations have this value; retire it instead of deleting it.')
  await page.getByRole('button', { name: 'Retire instead' }).click()
  await expect(value(page, 'Speaker', 'politician')).toContainText('Retired')

  // Narrowing to another tag would leave Jan Novák (a person) with a value that does not apply.
  await page.getByRole('button', { name: 'Edit Speaker' }).click()
  await page.getByLabel('Applies to tags').click()
  await page.getByRole('option', { name: fixture.tag('place').name }).click()
  await page.getByRole('option', { name: fixture.tag('person').name }).click()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByTestId('attribute-dialog-error')).toContainText('1 annotations with values of this attribute have a tag outside')
  await page.getByRole('button', { name: 'Cancel' }).click()
  await page.getByRole('button', { name: 'Yes' }).click()
  await expect(card(page, 'Speaker')).toContainText(`tags ${fixture.tag('person').name}`)

  // The whole attribute: deleting it is refused too, and it is retired instead and restored.
  await page.getByRole('button', { name: 'Delete Speaker' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Delete' }).click()
  await expect(page.getByRole('dialog').filter({ hasText: 'Still in use' })).toContainText('retire it instead')
  await page.getByRole('button', { name: 'Retire instead' }).click()
  await expect(card(page, 'Speaker')).toHaveClass(/attribute--retired/)
  await page.getByRole('button', { name: 'Restore Speaker' }).click()
  await expect(card(page, 'Speaker')).not.toHaveClass(/attribute--retired/)
  await expect(page.getByRole('button', { name: 'Retire Speaker' })).toBeVisible()
})

test('a deleted applicable tag is shown as such and is not sent again', async ({ page, request }) => {
  const headers = await headersOf(request)
  const tag = await request.post('/api/tags', {
    headers,
    params: { collection_id: chronicles.id },
    data: { name: 'Interview', shorthand: 'INT', color: '#888888', pictogram: 'mic', definition: 'An interview.' }
  })
  expect(tag.ok()).toBe(true)
  const tagId = (await tag.json() as { id: string }).id
  expect((await request.post(`${base}/attributes`, {
    headers, data: { name: 'Mood', cardinality: 'single', tag_ids: [tagId], values: [{ label: 'calm' }] }
  })).ok()).toBe(true)
  expect((await request.delete(`/api/tags/${tagId}`, { headers })).ok()).toBe(true)

  await useViewport(page, 'wide')
  await openAttributes(page)
  await expect(card(page, 'Mood')).toContainText('only deleted tags')

  // Adding a tag next to the deleted one is refused in the form until the deleted one is removed.
  await page.getByRole('button', { name: 'Edit Mood' }).click()
  await expect(page.getByTestId('attribute-deleted-tag')).toHaveText(/Deleted tag/)
  await page.getByLabel('Applies to tags').click()
  await page.getByRole('option', { name: fixture.tag('person').name }).click()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByRole('dialog')).toContainText('Remove the deleted tags, or leave the tags unchanged')
  await page.getByTestId('attribute-deleted-tag').locator('.q-chip__icon--remove').click()
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(card(page, 'Mood')).toContainText(`tags ${fixture.tag('person').name}`)
})
