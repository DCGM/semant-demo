import { expect, test, type Page } from '@playwright/test'

import { closePhoneNavigation, fixture, useViewport } from './support'

// Corpus overview (#254, #361): document counts of the whole public corpus or of the
// documents matching metadata filters, without signing in. The fixture store has three
// documents (chronicle "Kronika obce Lhota" 1851, letters "Dopisy z Prahy" 1902, gazette
// "Pražský věstník" without a year), all in `ces`, and declares no `library` property.

const DISTRIBUTIONS = '**/api/analytics/corpus/distributions'
const LIBRARY_YEARS = '**/api/analytics/corpus/library-years'
const card = (page: Page, key: string) => page.getByTestId(`corpus-${key}`)

async function openFromNavigation (page: Page) {
  await page.goto('/')
  await page.locator('.q-drawer--left .drawer-item').filter({ hasText: 'Corpus' }).click()
  await expect(page).toHaveURL(/#\/corpus$/)
}

/** The rows of a card's table (opened first), as cell texts. */
async function tableRows (page: Page, key: string): Promise<string[][]> {
  await card(page, key).getByText(/^Table: documents per/).click()
  const rows = card(page, key).locator('tbody tr')
  await expect(rows.first()).toBeVisible()
  // The rows count as visible while the table is still closed: Quasar's slide holds it at
  // height 0 for 100 ms, then opens it over 300 ms and moves the cards below. A click on one
  // of them in that time can miss (#429), so wait until the slide removes its inline height.
  await expect(card(page, key).locator('.q-expansion-item__content')).not.toHaveAttribute('style', /height/)
  return rows.evaluateAll((trs) => trs.map((tr) => Array.from(tr.querySelectorAll('th, td'), (c) => c.textContent?.trim() ?? '')))
}

test('an anonymous user opens the corpus overview from the navigation', async ({ page }) => {
  await openFromNavigation(page)

  await expect(page.getByTestId('corpus-scope')).toContainText('not your collections or the results of a search')
  await expect(page.getByTestId('corpus-total')).toHaveText('3')
  // Each document once, whatever its number of chunks (the chronicle has three).
  expect(fixture.document('chronicle').chunks).toHaveLength(3)

  await expect(card(page, 'years')).toContainText('2 of 3 documents (66.7 %) have a publication year; 1 unknown.')
  await expect(card(page, 'years').locator('svg').first()).toBeVisible()
  // The timeline opens on 1850–1909 (60 years: single years); long empty periods are one row.
  await expect(page.getByTestId('timeline-window')).toHaveText('1850–1909 · single years')
  expect(await tableRows(page, 'years')).toEqual([
    ['1850', '0'], ['1851', '1'], ['1852–1901 — no documents (50 years)', '0'], ['1902', '1'],
    ['1903–1909 — no documents (7 years)', '0'], ['Unknown or invalid year', '1']
  ])

  await expect(card(page, 'languages').locator('svg').first()).toBeVisible()
  expect(await tableRows(page, 'languages')).toEqual([['Czech (ces)', 'ces', '3'], ['Unknown', '—', '0']])

  // The store has no library property: unavailable, not a chart of zeros, not a filter, no heatmap.
  await expect(card(page, 'libraries')).toContainText('Not available')
  await expect(card(page, 'libraries').locator('svg')).toHaveCount(0)
  await expect(page.getByTestId('corpus-filters')).toContainText('does not record libraries')
  await expect(card(page, 'heatmap')).toContainText('Not available')
})

test('filters narrow every count to the matching documents until they are cleared', async ({ page }) => {
  await page.goto('/#/corpus')
  await expect(page.getByTestId('corpus-total')).toHaveText('3')

  await page.getByTestId('filter-year-min').fill('1850')
  await page.getByTestId('filter-year-max').fill('1901')
  await page.getByTestId('filter-apply').click()

  // Only the chronicle (1851): the letters are from 1902, the gazette has no year.
  await expect(page.getByTestId('corpus-total')).toHaveText('1')
  await expect(page.getByTestId('corpus-of-total')).toHaveText('of 3 documents in the corpus')
  await expect(page.getByTestId('corpus-applied-years')).toContainText('1850–1901')
  await expect(card(page, 'years')).toContainText('1 of 1 documents (100 %) have a publication year; 0 unknown.')
  expect(await tableRows(page, 'languages')).toEqual([['Czech (ces)', 'ces', '1'], ['Unknown', '—', '0']])

  // Title words ignore case, not diacritics. Enter adds the title and empties the field.
  await page.getByRole('button', { name: 'Remove filter Years 1850–1901' }).click()
  await expect(page.getByTestId('corpus-total')).toHaveText('3')
  await page.getByTestId('filter-title').fill('PRAŽ')
  await page.getByTestId('filter-title').press('Enter')
  await expect(page.getByTestId('corpus-applied-title')).toContainText('PRAŽ')
  await expect(page.getByTestId('filter-title')).toHaveValue('')
  await expect(page.getByTestId('corpus-total')).toHaveText('1')
  await expect(card(page, 'years')).toContainText('0 of 1 documents (0 %) have a publication year; 1 unknown.')

  // A second title is an alternative: the gazette or the letters ("Dopisy z Prahy").
  await page.getByTestId('filter-title').fill('dopisy')
  await page.getByTestId('filter-apply').click()
  await expect(page.getByTestId('corpus-total')).toHaveText('2')

  await page.getByRole('button', { name: 'Remove filter Title contains PRAŽ' }).click()
  await page.getByRole('button', { name: 'Remove filter Title contains dopisy' }).click()
  await page.getByTestId('filter-title').fill('praz')
  await page.getByTestId('filter-title').press('Enter')
  await expect(page.getByTestId('corpus-no-match')).toContainText('No documents match these filters')

  await page.getByTestId('corpus-clear-all').click()
  await expect(page.getByTestId('corpus-total')).toHaveText('3')
  await expect(page.getByTestId('corpus-applied')).toHaveCount(0)
})

test('zooming the timeline changes only the chart, applying its period filters every count', async ({ page }) => {
  await page.goto('/#/corpus')
  await expect(page.getByTestId('timeline-window')).toHaveText('1850–1909 · single years')

  await page.getByTestId('timeline-zoom-in').click()
  await expect(page.getByTestId('timeline-window')).toHaveText('1865–1894 · single years')
  await expect(page.getByTestId('timeline-outside')).toContainText('1 document before 1865 (year 1851); 1 document after 1894 (year 1902)')
  await expect(page.getByTestId('corpus-total')).toHaveText('3')

  await page.getByTestId('timeline-reset').click()
  await page.getByTestId('timeline-apply-period').click()
  await expect(page.getByTestId('corpus-applied-years')).toContainText('1850–1909')
  await expect(page.getByTestId('corpus-total')).toHaveText('2')
  await expect(page.getByTestId('filter-year-min')).toHaveValue('1850')
})

test('the overview fits a phone screen and lists the libraries of a synced store', async ({ page }) => {
  await useViewport(page, 'phone')
  await page.route(DISTRIBUTIONS, async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    body.libraries = { available: true, values: [{ value: 'mzk', count: 2 }], other_count: 0, unknown_count: 1 }
    await route.fulfill({ response, json: body })
  })
  await page.goto('/#/corpus')
  await closePhoneNavigation(page)

  await expect(card(page, 'libraries').locator('svg').first()).toBeVisible()
  expect(await tableRows(page, 'libraries')).toEqual([['Moravian Library (mzk)', 'mzk', '2'], ['Unknown', '—', '1']])
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect(overflow).toBeLessThanOrEqual(0)
  await expect(page.getByTestId('filter-libraries')).toBeEnabled()

  // The heatmap of a synced store (its counts stubbed: the fixture store has no libraries).
  await page.route(LIBRARY_YEARS, (route) => route.fulfill({
    json: {
      scope: 'searchable_corpus',
      unit: 'documents',
      filters: { year_min: null, year_max: null, title_contains: [], libraries: [], languages: [] },
      total_documents: 3,
      computed_at: '2026-10-22T12:00:00Z',
      available: true,
      rows: [
        { library: 'mzk', kind: 'value', total_documents: 2, years: [{ year: 1851, count: 1 }, { year: 1902, count: 1 }], unknown_year_count: 0 },
        { library: null, kind: 'unknown', total_documents: 1, years: [], unknown_year_count: 1 }
      ]
    }
  }))
  await page.getByTestId('heatmap-show').click()
  await expect(card(page, 'heatmap').locator('svg').first()).toBeVisible()
  for (const key of ['years', 'libraries', 'languages', 'heatmap']) {
    const box = await card(page, key).locator('svg').first().boundingBox()
    expect(box!.x + box!.width).toBeLessThanOrEqual(390)
  }
})

test('a failed overview offers Retry instead of empty charts', async ({ page }) => {
  let failures = 1
  await page.route(DISTRIBUTIONS, async (route) => {
    if (failures-- > 0) await route.fulfill({ status: 500, contentType: 'text/plain', body: 'Internal Server Error' })
    else await route.continue()
  })
  await page.goto('/#/corpus')

  await expect(page.getByRole('alert')).toContainText('could not be loaded')
  await expect(page.getByTestId('corpus-total')).toHaveCount(0)
  await page.getByRole('button', { name: 'Retry' }).click()
  await expect(page.getByTestId('corpus-total')).toHaveText('3')
})
