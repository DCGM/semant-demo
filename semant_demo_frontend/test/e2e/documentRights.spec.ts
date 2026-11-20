import { expect, test, type Page, type Route } from '@playwright/test'
import { ensureLoggedIn, fixture, useViewport } from './support'

// The document rights labels and the collection kept by links (#279). The fixture documents
// are all public, so these tests mark "Dopisy z Prahy" restricted (`public` false) and
// "Kronika obce Lhota" unknown (no `public`) in the API's answers; the rule itself is tested
// against the real store (tests/integration/test_document_rights.py).

const letters = fixture.document('letters')
const chronicle = fixture.document('chronicle')
const chronicles = fixture.collection('chronicles')

type Stored = { id: string, public?: boolean | null }

function withRights<T extends Stored> (document: T): T {
  if (document.id === letters.id) return { ...document, public: false }
  if (document.id === chronicle.id) {
    const rest = { ...document }
    delete rest.public
    return rest
  }
  return document
}

async function rewrite<T> (page: Page, url: string, change: (body: T) => unknown) {
  await page.route(url, async (route: Route) => {
    const response = await route.fetch()
    await route.fulfill({ response, json: change(await response.json()) })
  })
}

for (const viewport of ['wide', 'phone'] as const) {
  test(`collection document rows show Restricted and Access unknown (${viewport})`, async ({ page }) => {
    await useViewport(page, viewport)
    await rewrite<Stored[]>(page, `**/api/user_collections/${chronicles.id}/documents`, (body) => body.map(withRights))
    await ensureLoggedIn(page, 'owner')
    await page.goto(`/#/collections/${chronicles.id}/documents`)

    const row = (title: string) => page.locator('tr', { hasText: title })
    await expect(row(letters.properties.title).getByTestId('document-rights-label')).toHaveText('Restricted')
    await expect(row(chronicle.properties.title).getByTestId('document-rights-label')).toHaveText('Access unknown')
    await page.screenshot({ path: test.info().outputPath(`collection-rows-${viewport}.png`) })
  })
}

test('collection-scoped results are labelled and open the document through the collection', async ({ page }) => {
  await useViewport(page, 'wide')
  await rewrite<{ items: { document: Stored }[] }>(page, '**/api/search/documents', (body) => ({
    ...body, items: body.items.map(hit => ({ ...hit, document: withRights(hit.document) }))
  }))
  await ensureLoggedIn(page, 'owner')
  await page.goto('/#/search?year_max=1910')
  await page.getByRole('button', { name: 'Search filters' }).click()
  await page.getByLabel('Select a Collection').click()
  await page.getByRole('option', { name: chronicles.name }).click()
  await page.getByRole('button', { name: 'Search filters' }).click()
  await page.getByRole('combobox', { name: 'Search query' }).press('Enter')

  const card = page.locator('.document-result', { hasText: letters.properties.title })
  await expect(card.getByTestId('document-rights-label')).toHaveText('Restricted')
  await page.screenshot({ path: test.info().outputPath('scoped-results.png') })
  const open = card.getByTestId('document-result-open')
  await expect(open).toHaveAttribute('href', new RegExp(`collection=${chronicles.id}`))

  const read = page.waitForRequest(r => new URL(r.url()).pathname === `/api/document/${letters.id}`)
  await open.click()
  expect(new URL((await read).url()).searchParams.get('collection_id')).toBe(chronicles.id)
  await expect(page.getByTestId('document-error')).toHaveCount(0)
})

// Adding a document that is not public to another collection is intended, but gives it a new,
// lasting route there: Explore asks first, for a document and for a chunk (#789).
for (const action of ['Add Documents', 'Add Chunks'] as const) {
  test(`${action} asks before linking a restricted document to another collection`, async ({ page }) => {
    await useViewport(page, 'wide')
    const newspapers = fixture.collection('newspapers')
    await rewrite<{ items: { document_object: Stored }[] }>(page, '**/api/search/passages', (body) => ({
      ...body, items: body.items.map(hit => ({ ...hit, document_object: withRights(hit.document_object) }))
    }))
    // The adds are answered here: the shared fixture store keeps its membership.
    const adds: string[] = []
    await page.route(`**/api/user_collections/${newspapers.id}/**`, async (route) => {
      if (route.request().method() !== 'POST') return route.continue()
      adds.push(new URL(route.request().url()).pathname)
      await route.fulfill({ json: { outcome: 'complete', succeeded: [], failed: [], unattempted: [] } })
    })
    await ensureLoggedIn(page, 'owner')
    await page.goto('/#/search')
    await page.getByRole('combobox', { name: 'Search query' }).fill('Prahy')
    await page.getByRole('button', { name: 'Search filters' }).click()
    await page.getByLabel('Select a Collection').click()
    await page.getByRole('option', { name: chronicles.name }).click()
    await page.getByRole('button', { name: 'Search filters' }).click()
    await page.getByRole('combobox', { name: 'Search query' }).press('Enter')

    const result = page.locator('.search-result', { hasText: fixture.chunk('letters_1').text })
    await expect(result.getByTestId('document-rights-label')).toHaveText('Restricted')
    await result.getByRole('checkbox').click()
    const toolbar = page.locator('.selection-toolbar')
    await toolbar.getByLabel('Select Collection').click()
    await page.getByRole('option', { name: newspapers.name }).click()

    const dialog = page.getByRole('dialog')
    await toolbar.getByRole('button', { name: action }).click()
    await expect(dialog).toContainText('Add documents that are not public?')
    await expect(dialog).toContainText(`“${letters.properties.title}”`)
    await expect(dialog).toContainText('lasting access')
    if (action === 'Add Documents') await page.screenshot({ path: test.info().outputPath('add-restricted-confirm.png'), animations: 'disabled' })
    await dialog.getByRole('button', { name: 'Cancel' }).click()
    await expect(dialog).toHaveCount(0)
    expect(adds).toEqual([])

    await toolbar.getByRole('button', { name: action }).click()
    await dialog.getByRole('button', { name: 'Add anyway' }).click()
    await expect.poll(() => adds).toEqual([action === 'Add Documents'
      ? `/api/user_collections/${newspapers.id}/documents/${letters.id}`
      : `/api/user_collections/${newspapers.id}/chunks/${fixture.chunk('letters_1').id}`])
  })
}

test('adding public documents asks nothing', async ({ page }) => {
  await useViewport(page, 'wide')
  const newspapers = fixture.collection('newspapers')
  const adds: string[] = []
  await page.route(`**/api/user_collections/${newspapers.id}/**`, async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    adds.push(new URL(route.request().url()).pathname)
    await route.fulfill({ json: { outcome: 'complete', succeeded: [], failed: [], unattempted: [] } })
  })
  await ensureLoggedIn(page, 'owner')
  await page.goto('/#/search')
  await page.getByRole('combobox', { name: 'Search query' }).fill('Prahy')
  await page.getByRole('combobox', { name: 'Search query' }).press('Enter')
  await page.locator('.search-result', { hasText: fixture.chunk('letters_1').text }).getByRole('checkbox').click()
  const toolbar = page.locator('.selection-toolbar')
  await toolbar.getByLabel('Select Collection').click()
  await page.getByRole('option', { name: newspapers.name }).click()
  await toolbar.getByRole('button', { name: 'Add Chunks' }).click()

  await expect.poll(() => adds).toHaveLength(1)
  await expect(page.getByRole('dialog')).toHaveCount(0)
})
