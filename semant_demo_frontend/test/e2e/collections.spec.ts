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

test('collections the table no longer shows leave its selection', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openCollections(page)
  await page.getByRole('button', { name: 'Table' }).click()
  await page.getByRole('checkbox').first().click() // the header box selects every row
  await expect(page.locator('.bulk-count')).toHaveText(/^[2-9]\d* selected$/)

  await page.getByPlaceholder('Search collections...').fill(fixture.collection('newspapers').name)
  await expect(page.locator('.bulk-count')).toHaveText('1 selected')
  await page.getByPlaceholder('Search collections...').fill('')
  await expect(page.locator('.bulk-count')).toHaveText('1 selected') // shown again, not selected again
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

test('collections table sorts Created and Updated chronologically', async ({ page, request }) => {
  await ensureLoggedIn(page, 'owner')

  const headers = {
    Authorization: `Bearer ${await apiToken(request, 'owner')}`
  }

  // Unique names prevent collisions with other tests.
  const prefix = `date-sort-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

  const testCollections = [
    {
      name: `${prefix}-A`,
      createdAt: '2026-01-09T12:00:00Z',
      updatedAt: '2026-01-10T12:00:00Z'
    },
    {
      name: `${prefix}-B`,
      createdAt: '2026-01-10T12:00:00Z',
      updatedAt: '2025-12-20T12:00:00Z'
    },
    {
      name: `${prefix}-C`,
      createdAt: '2025-12-20T12:00:00Z',
      updatedAt: '2026-01-09T12:00:00Z'
    },
    {
      name: `${prefix}-D`,
      createdAt: '2026-01-09T20:00:00Z',
      updatedAt: '2026-01-09T20:00:00Z'
    }
  ]

  const created: Array<{
    id: string
    createdAt: string
    updatedAt: string
  }> = []

  try {
    // Create three real collections through the API.
    for (const collection of testCollections) {
      const response = await request.post('/api/user_collections', {
        headers,
        data: {
          name: collection.name,
          color: '#1976d2'
        }
      })

      expect(response.status()).toBe(201)

      const { id } = await response.json() as { id: string }

      created.push({
        id,
        createdAt: collection.createdAt,
        updatedAt: collection.updatedAt
      })
    }

    // Override only the dates of collections created by this test.
    const datesById = new Map(
      created.map((collection) => [
        collection.id,
        {
          created_at: collection.createdAt,
          updated_at: collection.updatedAt
        }
      ])
    )

    await page.route('**/api/user_collections', async (route) => {
      if (route.request().method() !== 'GET') {
        return route.continue()
      }

      const response = await route.fetch()

      const collections = await response.json() as Array<{
        id: string
        created_at: string
        updated_at: string
      }>

      const modified = collections.map((collection) => ({
        ...collection,
        ...(datesById.get(collection.id) ?? {})
      }))

      await route.fulfill({ response, json: modified })
    })

    // Show only the collections created by this test.
    await openCollections(page)
    await page.getByRole('button', { name: /^All \(\d+\)$/ }).click()
    await page.getByRole('button', { name: 'Table' }).click()
    await page.getByPlaceholder('Search collections...').fill(prefix)

    const names = page.locator('.q-table tbody tr td:nth-child(3)')
    await expect(names).toHaveCount(4)

    const [a, b, c, d] = testCollections.map((collection) => collection.name)

    // Name: ascending (default).
    await expect(names).toHaveText([a, b, c, d])

    // Name: descending.
    await page.getByRole('columnheader', { name: 'Name' }).click()
    await expect(names).toHaveText([d, c, b, a])

    // Created: ascending (oldest first).
    const createdHeader = page.getByRole('columnheader', { name: 'Created' })
    await createdHeader.click()
    await expect(names).toHaveText([c, a, d, b])

    // Created: descending (newest first).
    await createdHeader.click()
    await expect(names).toHaveText([b, d, a, c])

    // Updated: ascending (oldest first).
    const updatedHeader = page.getByRole('columnheader', { name: 'Updated' })
    await updatedHeader.click()
    await expect(names).toHaveText([b, c, d, a])

    // Updated: descending (newest first).
    await updatedHeader.click()
    await expect(names).toHaveText([a, d, c, b])
  } finally {
    // Delete every collection successfully created by this test,
    // even if one of the sorting assertions fails.
    const results = await Promise.all(
      created.map(async (collection) => {
        const response = await request.delete(
          `/api/user_collections/${collection.id}`,
          { headers }
        )
        return { id: collection.id, status: response.status() }
      })
    )

    for (const result of results) {
      expect(result.status, `Failed to delete collection ${result.id}`).toBe(204)
    }
  }
})
