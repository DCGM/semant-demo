import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

import { apiToken, deleteAddedAttributes, ensureLoggedIn, fixture, useViewport } from './support'

// Attribute definitions of a collection (#331, ADR 0011): the owner and shared users create
// attributes with values, rename and retire them; a used value or attribute is not deleted
// but can be retired, and narrowing the tags of a used attribute is refused with the count.

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

/** Creates "Speaker" (person tag) with one value and gives it to the approved Jan Novák. */
async function speakerOnNovak (request: APIRequestContext) {
  const headers = { Authorization: `Bearer ${await apiToken(request, 'owner')}` }
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
})

test('the owner defines an attribute with values, renames and retires it', async ({ page }) => {
  await useViewport(page, 'wide')
  await openAttributes(page)
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
  await page.getByLabel('Value 3', { exact: true }).fill('not known')
  await page.getByTestId('attribute-dialog-value').nth(2).getByLabel('Kind').click()
  await page.getByRole('option', { name: 'Unknown' }).click()
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
  await expect(card(page, 'Speaker').getByTestId('attribute-value-label')).toHaveText(['politician', 'not known'])

  // The list is what the backend stores.
  await page.reload()
  await expect(card(page, 'Speaker').getByTestId('attribute-value-label')).toHaveText(['politician', 'not known'])
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
})
