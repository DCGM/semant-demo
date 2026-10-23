import { expect, test, type Locator, type Page } from '@playwright/test'
import { apiToken, ensureLoggedIn, fixture } from './support'

// The collections page (#479): which collections are shown, the tile size and the table's
// column widths, and the collection overview's members and AI suggestion count.

async function openCollections (page: Page) {
  await page.locator('.q-drawer').getByText('Collections', { exact: true }).click()
  await expect(page.getByPlaceholder('Search collections...')).toBeVisible()
}

/** Drags the element's centre by `dx` pixels. */
async function dragBy (page: Page, target: Locator, dx: number) {
  const box = (await target.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + dx, box.y + box.height / 2, { steps: 5 })
  await page.mouse.up()
}

test('the collections page shows my, shared or all collections and remembers the choice', async ({ page }) => {
  await ensureLoggedIn(page, 'annotator')
  await openCollections(page)
  const shared = page.getByText(fixture.collection('chronicles').name, { exact: true })
  await expect(shared).toBeVisible()

  await page.getByRole('button', { name: /^My \(\d+\)$/ }).click()
  await expect(shared).toHaveCount(0)
  await page.getByRole('button', { name: /^Shared with me \(\d+\)$/ }).click()
  await expect(shared).toBeVisible()
  await expect(page.getByTitle('Create new collection')).toHaveCount(0) // a new one would be mine

  await page.reload()
  await expect(shared).toBeVisible()
  await page.getByRole('button', { name: /^My \(\d+\)$/ }).click()
  await expect(shared).toHaveCount(0)
  await page.getByRole('button', { name: 'Table' }).click()
  await expect(page.locator('.q-table__top')).toContainText(/Collections \(\d+ items?\)/)
  await expect(shared).toHaveCount(0) // the table shows the same choice
  await page.getByRole('button', { name: /^All \(\d+\)$/ }).click()
  await expect(shared).toBeVisible()
})

test('the tile size slider changes and remembers the tile width', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openCollections(page)
  await page.getByRole('button', { name: 'Tiles' }).click()
  const tile = page.locator('.collection-tiles > *').first()
  const slider = page.locator('.tile-size .q-slider')
  const sliderBox = (await slider.boundingBox())!

  await page.mouse.click(sliderBox.x + 2, sliderBox.y + sliderBox.height / 2)
  const small = (await tile.boundingBox())!.width
  await page.mouse.click(sliderBox.x + sliderBox.width - 2, sliderBox.y + sliderBox.height / 2)
  await expect.poll(async () => (await tile.boundingBox())!.width).toBeGreaterThan(small)
  const large = (await tile.boundingBox())!.width

  await page.reload()
  await expect.poll(async () => (await tile.boundingBox())!.width).toBeCloseTo(large, 0)
})

test('the collections table columns are resized by dragging and reset by a double-click', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openCollections(page)
  await page.getByRole('button', { name: 'Table' }).click()
  const owner = page.getByRole('columnheader', { name: 'Owner' })
  const handle = page.getByRole('separator', { name: 'Resize the Owner column' })
  const natural = (await owner.boundingBox())!.width

  await dragBy(page, handle, 120)
  await expect.poll(async () => (await owner.boundingBox())!.width).toBeGreaterThan(natural + 100)
  await page.reload()
  await expect.poll(async () => (await owner.boundingBox())!.width).toBeGreaterThan(natural + 100)

  await handle.dblclick()
  await expect.poll(async () => (await owner.boundingBox())!.width).toBeLessThan(natural + 20)

  // Narrower than its text: the column keeps the width and cuts the text.
  const name = page.getByRole('columnheader', { name: 'Name' })
  await dragBy(page, page.getByRole('separator', { name: 'Resize the Name column' }), -((await name.boundingBox())!.width - 70))
  await expect.poll(async () => (await name.boundingBox())!.width).toBeLessThan(80)
  const cell = page.getByRole('cell', { name: fixture.collection('chronicles').name, exact: true })
  await expect.poll(async () => (await cell.boundingBox())!.width).toBeLessThan(80)
})

test('the collection overview lists the members and counts the unresolved AI suggestions', async ({ page, request }) => {
  const collection = fixture.collection('chronicles')
  const counts = await request.get(`/api/user_collections/${collection.id}/annotations/counts`, {
    headers: { Authorization: `Bearer ${await apiToken(request, 'owner')}` }
  })
  expect(counts.ok()).toBe(true)
  const { suggestions } = await counts.json() as { suggestions: number }

  await ensureLoggedIn(page, 'owner')
  await openCollections(page)
  await page.getByText(collection.name, { exact: true }).click()

  const sharedWith = page.getByRole('row', { name: /^Shared with/ })
  await expect(sharedWith).toContainText(fixture.user('annotator').name)
  await expect(page.locator('.stat-card').filter({ hasText: 'Unresolved AI Suggestions' })).toContainText(String(suggestions))

  await sharedWith.getByRole('link', { name: 'Manage' }).click()
  await expect(page.getByText('Share with a user')).toBeVisible()
})
