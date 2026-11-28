import { expect, test, type Locator } from '@playwright/test'
import { ensureLoggedIn, fixture, openDocument, sidebarPanelButton } from './support'

// Tag arrows scroll the inner virtual list without moving the entire sidebar.
// The selected card may remain below the outer viewport until manual scrolling.
async function expectNavigationWithoutSidebarScroll(nav: Locator, sidebar: Locator) {
  await expect(nav).toBeInViewport()
  await expect.poll(() => sidebar.evaluate((el) => el.scrollTop)).toBe(0)
  await expect.poll(() => nav.evaluate(() => {
    const card = document.querySelector<HTMLElement>('.auto-span-card.is-highlighted')
    const list = card?.closest<HTMLElement>('.auto-span-list')
    if (!card || !list || !card.isConnected) return false
    const cardRect = card.getBoundingClientRect()
    const listRect = list.getBoundingClientRect()
    return cardRect.top >= listRect.top - 1 && cardRect.bottom <= listRect.bottom + 1
  })).toBe(true)
}

test('tag arrows scroll suggestions without scrolling the sidebar', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 650 })
  const chunkId = fixture.chunk('chronicle_1').id
  const sourceId = fixture.span('lhota_automatic').id

  // Many proposals force navigation to cards outside the mounted virtual slice.
  await page.route('**/api/tag_spans/batch', async (route) => {
    const response = await route.fetch()
    const spans = await response.json() as Record<string, Record<string, unknown>[]>
    const source = spans[chunkId]?.find((span) => span.id === sourceId)
    if (source) {
      spans[chunkId] = [
        ...spans[chunkId],
        ...Array.from({ length: 120 }, (_, i) => ({
          ...source,
          tagId: fixture.tag('person').id,
          id: `5e3b0000-0000-4000-8000-${(0xc000 + i).toString(16).padStart(12, '0')}`,
          start: 60 + (i % 12),
          end: 62 + (i % 12),
          confidence: 0.99,
          reason: `Synthetic proposal ${i}`
        }))
      ]
    }
    await route.fulfill({ response, json: spans })
  })

  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Tagging').click()
  await expect(page.getByTestId('proposal-match-count')).toContainText('121 matches')

  // Reproduce the problematic layout: Run options and filters are expanded.
  const options = page.getByTestId('ai-run-options')
  if (!(await options.isVisible())) await page.getByTestId('ai-options-toggle').click()
  await page.getByTestId('proposal-filters-toggle').click()
  await page.getByTestId('proposal-tag-filter').click()
  await page.getByRole('option', { name: fixture.tag('person').name, exact: true }).click()
  await expect(page.getByTestId('proposal-match-count')).toContainText('120 matches')
  const nav = page.locator('.ai-run-options .ai-tag-list-row')
    .filter({ hasText: fixture.tag('person').name }).locator('.ai-tag-nav')
  const sidebar = page.locator('.q-drawer .scroll.q-px-md.q-pb-md')
    .filter({ has: page.locator('.ai-assist-panel') })
  // The tag list is part of the normal panel flow, not a sticky overlay.
  await expect.poll(() => nav.evaluate((el) =>
    getComputedStyle(el.closest('.ai-tag-list')!).position)).toBe('static')
  await sidebar.evaluate((el) => { el.scrollTop = 0 })

  // Previous from no selection goes to a deep, initially unmounted suggestion.
  await nav.locator('button').first().click()
  await expectNavigationWithoutSidebarScroll(nav, sidebar)
  await expect.poll(() => page.getByTestId('ai-suggestion-list').evaluate((el) => el.scrollTop))
    .toBeGreaterThan(0)
  await expect(page.getByTestId('proposal-match-count')).toContainText('120 matches')

  await nav.locator('button').last().click()
  await expectNavigationWithoutSidebarScroll(nav, sidebar)

  // Navigation still expands Pending suggestions, without moving the outer sidebar.
  await page.getByTestId('pending-suggestions-toggle').click()
  await expect(page.getByTestId('pending-suggestions-toggle')).toHaveAttribute('aria-expanded', 'false')
  await sidebar.evaluate((el) => { el.scrollTop = 0 })
  await nav.locator('button').first().click()
  await expect(page.getByTestId('pending-suggestions-toggle')).toHaveAttribute('aria-expanded', 'true')
  await expectNavigationWithoutSidebarScroll(nav, sidebar)

  // The alternate navigation shown when Run options are folded behaves the same way.
  await page.getByTestId('ai-options-toggle').click()
  const foldedNav = page.getByTestId('ai-folded-nav').locator('.ai-tag-list-row')
    .filter({ hasText: fixture.tag('person').name }).locator('.ai-tag-nav')
  await sidebar.evaluate((el) => { el.scrollTop = 0 })
  await foldedNav.locator('button').last().click()
  await expectNavigationWithoutSidebarScroll(foldedNav, sidebar)

  // Manually scrolling the sidebar reveals the already-highlighted card.
  await sidebar.evaluate((el) => { el.scrollTop = el.scrollHeight })
  await expect(page.locator('.auto-span-card.is-highlighted')).toBeInViewport()
})
