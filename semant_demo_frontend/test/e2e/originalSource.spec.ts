import { expect, test, type Page } from '@playwright/test'

import { editSearchResults, ensureLoggedIn, fixture, openDocument, search, sidebarPanelButton } from './support'

// Links to the original digitized document in its digital library (#255). The fixture
// store declares no `library`; the answers get one here, as a synced store has.

const chronicle = fixture.document('chronicle')
const chronicle1 = fixture.chunk('chronicle_1')
const viewer = (library: string, document: string, page?: string) =>
  `https://www.digitalniknihovna.cz/${library}/view/uuid:${document}${page ? `?page=uuid:${page}` : ''}`

type Hit = { text: string, document_object: { id: string, library?: string | null } }

/** The chronicle's hits come from `mzk`; other documents keep no library. */
const chronicleFromMzk = (page: Page) => editSearchResults(page, (body) => {
  for (const hit of body.results as unknown as Hit[]) {
    if (hit.document_object.id === chronicle.id) hit.document_object.library = 'mzk'
  }
})

/** Adds `library` to the document answers of `route` (a JSON object or one with `document`). */
async function withLibrary (page: Page, route: string, library: string) {
  await page.route(route, async (r) => {
    const response = await r.fetch()
    const body = await response.json() as { id?: string, library?: string, document?: { library?: string } }
    if (body.document) body.document.library = library
    else body.library = library
    await r.fulfill({ response, json: body })
  })
}

test('search results and their context view open the original at the passage\'s page', async ({ page }) => {
  await chronicleFromMzk(page)
  await withLibrary(page, '**/api/documents/*/chunks/*/window?*', 'mzk')
  await search(page, 'Lhota')

  const card = page.locator('.search-result', { hasText: chronicle1.text })
  const link = card.getByRole('link', { name: /View in digital library \(MZK, opens in a new tab\)/ })
  await expect(link).toHaveAttribute('href', viewer('mzk', chronicle.id, chronicle1.start_page_id))
  await expect(link).toHaveAttribute('target', '_blank')
  await expect(link).toHaveAttribute('rel', 'noopener noreferrer')

  // The internal context view stays separate and links the matched passage's page too.
  await card.getByTestId('view-context').click()
  const context = page.getByTestId('chunk-context-header')
  await expect(context.getByTestId('original-source-link'))
    .toHaveAttribute('href', viewer('mzk', chronicle.id, chronicle1.start_page_id))
})

test('results without a library keep their source title but offer no link', async ({ page }) => {
  await chronicleFromMzk(page)
  await search(page, 'Slavia')

  const gazette = page.locator('.search-result', { hasText: fixture.chunk('gazette_1').text })
  await expect(gazette.locator('.search-result__source')).toContainText(fixture.document('gazette').properties.title as string)
  await expect(gazette.getByTestId('original-source-link')).toHaveCount(0)
})

test('the document view links the original document', async ({ page }) => {
  await withLibrary(page, `**/api/document/${chronicle.id}`, 'nkp')
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')

  const header = page.locator('.doc-header')
  await expect(header.getByTestId('original-source-link')).toHaveAttribute('href', viewer('nkp', chronicle.id))
  await sidebarPanelButton(page, 'Document').click()
  await expect(page.locator('.q-drawer--right').getByTestId('original-source-link'))
    .toHaveAttribute('href', viewer('nkp', chronicle.id))
})

test('Chat Assistant sources link their originals', async ({ page }) => {
  const source = (id: string, library: string | null) => ({
    id: `${id}c`,
    text: `Source ${id}`,
    start_page_id: chronicle1.start_page_id,
    from_page: 1,
    to_page: 1,
    document: chronicle.id,
    order: 0,
    document_object: { id: chronicle.id, library, title: `Title ${id}` }
  })
  await page.route('**/api/rag', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      rag_answer: 'An answer.', sources: [source('a', 'mzk'), source('b', null)], response_id: 'r1', time_spent: 1
    })
  }))
  await page.goto('/#/rag')
  await page.getByPlaceholder('Vaše otázka?').fill('Question')
  await page.getByPlaceholder('Vaše otázka?').press('Enter')
  await page.getByText('Sources', { exact: true }).click()

  const dialog = page.getByRole('dialog')
  const items = dialog.locator('.q-item')
  await expect(items.filter({ hasText: 'Title a' }).getByTestId('original-source-link'))
    .toHaveAttribute('href', viewer('mzk', chronicle.id, chronicle1.start_page_id))
  await expect(items.filter({ hasText: 'Title b' })).toBeVisible()
  await expect(items.filter({ hasText: 'Title b' }).getByTestId('original-source-link')).toHaveCount(0)
})
