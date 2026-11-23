import { expect, test, type Page, type Request } from '@playwright/test'

import { ensureLoggedIn, fixture, useViewport } from './support'

// The collection page and Explore (#795, #622): the Overview tab charts the collection's
// documents; "Explore this collection" and a clicked bar open Explore with the collection as its
// scope, handed over in memory, never in the URL. In the fixture corpus, "Kroniky a dopisy"
// holds the chronicle (1851) and the letters (1902), both `ces`, no library; "Noviny" holds
// other documents.

const chronicles = fixture.collection('chronicles')
const hash = (page: Page) => decodeURIComponent(new URL(page.url()).hash).replace(/\+/g, ' ')
const chip = (page: Page, text: string) => page.locator('.active-filter-chip', { hasText: text })
const isDocumentSearch = (r: Request) => new URL(r.url()).pathname.endsWith('/api/search/documents') && r.method() === 'POST'
const isDistributions = (r: Request) => new URL(r.url()).pathname.endsWith('/api/analytics/corpus/distributions') && r.method() === 'POST'
const documentTitles = (page: Page) => page.getByTestId('document-result-open')
const bar = (page: Page, card: string, category: string) =>
  page.getByTestId(card).locator(`[aria-roledescription="bar"][aria-label*="Click to filter by ${category}"]`).first()

/** The request bodies of one kind from now on. */
function bodies (page: Page, kind: (r: Request) => boolean) {
  const seen: Record<string, unknown>[] = []
  page.on('request', (r) => { if (kind(r)) seen.push(r.postDataJSON()) })
  return seen
}

/**
 * Opens the collection's Overview tab within the app (a hash change, no reload), so kept-alive
 * Explore stays as it was. Not by clicking the Collections list: with the list already in the
 * store, it renders at once and again when its fresh answer arrives, and a click in between can
 * be lost (seen in CI).
 */
async function openCollection (page: Page, id: string) {
  await page.evaluate((hash) => { window.location.hash = hash }, `#/collections/${id}/overview`)
  await expect(page.getByTestId('explore-collection')).toBeVisible()
}

for (const viewport of ['wide', 'phone'] as const) {
  test(`the Overview tab charts the collection's documents; a clicked bar explores them (${viewport})`, async ({ page }) => {
    await useViewport(page, viewport)
    await ensureLoggedIn(page, 'owner')
    const counted = page.waitForRequest(isDistributions)
    await page.goto(`/#/collections/${chronicles.id}/overview`)
    expect((await counted).postDataJSON()).toMatchObject({ user_collection_id: chronicles.id })

    const charts = page.getByTestId('collection-document-charts')
    await expect(charts.getByTestId('charts-scope')).toContainText('2 documents of collection Kroniky a dopisy.')
    await expect(page.locator('.stat-card').filter({ hasText: 'Documents in Collection' }).locator('.stat-value')).toHaveText('2')
    await expect(charts.getByTestId('corpus-years')).toContainText('2 of 2 collection documents (100 %) have a publication year')
    // A click opens Explore, which the charts say, instead of filtering this page.
    await expect(charts.getByTestId('corpus-years')).toContainText('a filter opens these documents in Explore.')
    await expect(charts.getByTestId('timeline-apply-period')).toContainText('Explore 1850–1909')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)

    const explored = page.waitForRequest(isDistributions)
    await bar(page, 'corpus-languages', 'Czech (ces)').click()
    expect((await explored).postDataJSON()).toMatchObject({
      filters: { languages: ['ces'], libraries: [], year_min: null, year_max: null },
      user_collection_id: chronicles.id
    })
    expect(hash(page)).toBe('#/search?languages=ces&mode=documents&view=visualizations')
    await expect(page.getByTestId('charts-collection-name')).toHaveText('Kroniky a dopisy')
    await expect(page.getByTestId('charts-total')).toHaveText('2')
    await expect(chip(page, 'Kroniky a dopisy')).toBeVisible()
  })
}

test('"Explore this collection" scopes Explore to it, also when Explore was left with the same URL and another collection', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await page.goto('/#/search')
  // Explore scoped to another collection, with the URL the hand-off goes to.
  await page.getByRole('button', { name: 'Search filters' }).click()
  await page.getByLabel('Select a Collection').click()
  await page.getByRole('option', { name: 'Noviny' }).click()
  await page.getByRole('button', { name: 'Search filters' }).click()
  await page.getByRole('combobox', { name: 'Search query' }).press('Enter')
  await expect(chip(page, 'Noviny')).toBeVisible()
  expect(hash(page)).toBe('#/search?mode=documents')

  await openCollection(page, chronicles.id)
  const searches = bodies(page, isDocumentSearch)
  await page.getByTestId('explore-collection').click()

  await expect(documentTitles(page)).toHaveCount(2)
  expect(hash(page)).toBe('#/search?mode=documents') // the collection is not in the URL
  await expect(chip(page, 'Kroniky a dopisy')).toBeVisible()
  await expect(chip(page, 'Noviny')).toHaveCount(0)
  // No search of the previous scope, or of none, ran for the hand-off.
  expect(searches.map(body => body.user_collection_id)).toEqual([chronicles.id])
})

test('a collection that can no longer be read is left out with a notice, not searched', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await page.goto(`/#/collections/${chronicles.id}/overview`)
  await expect(page.getByTestId('explore-collection')).toBeVisible()
  // Meanwhile it was unshared or deleted: the user's collections no longer list it.
  await page.route(url => url.pathname.endsWith('/api/user_collections'), async (route) => {
    if (route.request().method() !== 'GET') return route.continue()
    const response = await route.fetch()
    const listed = await response.json() as { id: string }[]
    await route.fulfill({ response, json: listed.filter(c => c.id !== chronicles.id) })
  })
  const searches = bodies(page, isDocumentSearch)

  await page.getByTestId('explore-collection').click()

  await expect(page.getByText('The collection is not searched: it no longer exists or is no longer shared with you.')).toBeVisible()
  await expect(documentTitles(page)).toHaveCount(3) // the corpus, as the URL says, without the collection
  await expect(chip(page, 'Kroniky a dopisy')).toHaveCount(0)
  expect(searches.map(body => body.user_collection_id ?? null)).toEqual([null])
})

test('a member the collection is shared with sees its charts and can explore it', async ({ page }) => {
  await ensureLoggedIn(page, 'annotator')
  await page.goto(`/#/collections/${chronicles.id}/overview`)
  await expect(page.getByTestId('collection-document-charts').getByTestId('charts-total')).toHaveText('2')

  const searched = page.waitForRequest(isDocumentSearch)
  await page.getByTestId('explore-collection').click()
  expect((await searched).postDataJSON().user_collection_id).toBe(chronicles.id)
  await expect(documentTitles(page)).toHaveCount(2)
})

test('the collection check ends also when the Collections page loads the list meanwhile', async ({ page }) => {
  // Review of #796: the check waited for a load of the store that another page replaced, and
  // Explore stayed on "loading" for good.
  await ensureLoggedIn(page, 'owner')
  await openCollection(page, chronicles.id)
  const held: (() => void)[] = []
  let first = true
  await page.route(url => url.pathname.endsWith('/api/user_collections'), async (route) => {
    if (route.request().method() === 'GET' && first) {
      first = false
      await new Promise<void>(resolve => held.push(resolve))
    }
    await route.continue()
  })

  await page.getByTestId('explore-collection').click()
  await expect.poll(() => held.length).toBe(1) // the check's list, held
  await page.locator('.q-drawer').getByText('Collections', { exact: true }).click()
  await expect(page.getByText(chronicles.name, { exact: true })).toBeVisible()
  held[0]()
  await page.locator('.q-drawer').getByText('Document search', { exact: true }).click()

  await expect(documentTitles(page)).toHaveCount(2)
  await expect(chip(page, 'Kroniky a dopisy')).toBeVisible()
})

test('while the collection is checked, Explore shows no counts of its earlier filters under the new ones', async ({ page }) => {
  // Review of #796: Explore charted the collection for one filter; a bar of another filter
  // clicked on its Overview showed the earlier counts under the new filter until the check ended.
  await ensureLoggedIn(page, 'owner')
  await openCollection(page, chronicles.id)
  const charts = page.getByTestId('collection-document-charts')
  await expect(charts.getByTestId('charts-total')).toHaveText('2')
  await charts.getByTestId('timeline-apply-period').click()
  await expect(chip(page, 'Kroniky a dopisy')).toBeVisible()
  await expect(page.getByTestId('charts-total')).toHaveText('2')
  expect(hash(page)).toBe('#/search?year_min=1850&year_max=1909&mode=documents&view=visualizations')

  await openCollection(page, chronicles.id)
  const held: (() => void)[] = []
  let first = true
  await page.route(url => url.pathname.endsWith('/api/user_collections'), async (route) => {
    if (route.request().method() === 'GET' && first) {
      first = false
      await new Promise<void>(resolve => held.push(resolve))
    }
    await route.continue()
  })
  const counts = bodies(page, isDistributions)
  await bar(page, 'corpus-languages', 'Czech (ces)').click()
  await expect.poll(() => held.length).toBe(1) // the check's list, held

  expect(hash(page)).toBe('#/search?languages=ces&mode=documents&view=visualizations')
  await expect(chip(page, 'Kroniky a dopisy')).toBeVisible()
  await expect(page.getByTestId('charts-total')).toHaveCount(0)
  await expect(page.getByTestId('explore-visualizations').getByTestId('charts-loading')).toContainText('Checking the collection…')
  await expect(page.getByTestId('corpus-years')).toHaveCount(0)
  expect(counts).toEqual([]) // not counted before the check ends

  held[0]()
  await expect(page.getByTestId('charts-total')).toHaveText('2')
  expect(counts).toEqual([expect.objectContaining({
    filters: expect.objectContaining({ languages: ['ces'], year_min: null, year_max: null }),
    user_collection_id: chronicles.id
  })])
})

// The included passages (#807): "Kroniky a dopisy" includes four passages, all `ces`; one holds
// subject_domain values, one `formal` and one `informal` style.
const isPassageCounts = (r: Request) => new URL(r.url()).pathname.endsWith('/api/analytics/collection/passages') && r.method() === 'POST'

for (const viewport of ['wide', 'phone'] as const) {
  test(`the Overview tab charts the collection's passages, one classification at a time (${viewport})`, async ({ page }) => {
    await useViewport(page, viewport)
    await ensureLoggedIn(page, 'owner')
    const asked = bodies(page, isPassageCounts)
    await page.goto(`/#/collections/${chronicles.id}/overview`)

    const charts = page.getByTestId('collection-passage-charts')
    await expect(charts.getByTestId('passage-charts-scope')).toContainText('4 passages included in collection Kroniky a dopisy.')
    await expect(page.locator('.stat-card').filter({ hasText: 'Chunks in Collection' }).locator('.stat-value')).toHaveText('4')
    await expect(charts.getByTestId('passage-languages')).toContainText('Every passage has a detected language.')
    await charts.getByTestId('passage-languages-table').click()
    await expect(charts.getByTestId('passage-languages-table').locator('tbody tr').first()).toContainText('Czech (ces)')
    // The first classification: subject_domain, held by one passage.
    await expect(charts.getByTestId('passage-classification-occurring')).toContainText('2 of')
    await charts.getByTestId('passage-classification-table').click()
    await expect(charts.getByTestId('passage-classification-table').locator('code')).toHaveText(
      ['ddc_900_history_geography', 'news_and_current_affairs'], { useInnerText: true })
    await expect(charts.getByTestId('passage-classification-table').locator('tbody tr').last()).toContainText('Without a value')
    await expect(charts.getByTestId('passage-classification-table').locator('tbody tr').last()).toContainText('3')
    expect(asked).toEqual([
      { user_collection_id: chronicles.id, dimension: null },
      { user_collection_id: chronicles.id, dimension: 'subject_domain' }
    ])

    // Another classification: asked for alone.
    await charts.getByTestId('passage-dimension').click()
    await page.getByRole('option', { name: /style/i }).click()
    await expect(charts.getByTestId('passage-classification-table').locator('code')).toHaveText(['formal', 'informal'], { useInnerText: true })
    await expect(charts.getByTestId('passage-classification-table').locator('tbody tr').last()).toContainText('2')
    expect(asked.slice(2)).toEqual([{ user_collection_id: chronicles.id, dimension: 'style' }])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  })
}
