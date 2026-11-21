import { expect, test, type Locator } from '@playwright/test'
import { ensureLoggedIn, fixture, openDocument, sidebarPanelButton } from './support'

// Both the tag navigation and the chosen card must remain visible in the
// outer sidebar, even when the options/filters take up most of its height.
async function expectNavigationAndCardVisible(nav: Locator) {
  await expect.poll(() => nav.evaluate((element) => {
    const outer = element.closest<HTMLElement>('.sidebar-panel')?.parentElement
    const navList = element.closest<HTMLElement>('.ai-tag-list')
    const card = document.querySelector<HTMLElement>('.auto-span-card.is-highlighted')
    const list = card?.closest<HTMLElement>('.auto-span-list')
    if (!outer || !navList || !card || !list) return false
    const outerRect = outer.getBoundingClientRect()
    const navRect = navList.getBoundingClientRect()
    const cardRect = card.getBoundingClientRect()
    const listRect = list.getBoundingClientRect()
    const stickyBottom = navRect.top <= outerRect.top + 1 ? navRect.bottom : outerRect.top
    return navRect.top >= outerRect.top - 1 && navRect.bottom <= outerRect.bottom + 1 &&
      cardRect.top >= Math.max(outerRect.top, listRect.top, stickyBottom) - 1 &&
      cardRect.bottom <= Math.min(outerRect.bottom, listRect.bottom, window.innerHeight) + 1
  })).toBe(true)
}

test('tag arrows keep navigation visible with expanded controls and folded suggestions', async ({ page }) => {
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
  await expect(page.getByTestId('proposal-match-count')).toContainText('121 of 121 matching')

  // Reproduce the problematic layout: Run options and filters are expanded.
  const options = page.getByTestId('ai-run-options')
  if (!(await options.isVisible())) await page.getByTestId('ai-options-toggle').click()
  await page.getByTestId('proposal-filters-toggle').click()
  await page.getByTestId('proposal-tag-filter').click()
  await page.getByRole('option', { name: fixture.tag('person').name, exact: true }).click()
  await expect(page.getByTestId('proposal-match-count')).toContainText('120 of 121 matching')
  const nav = page.locator('.ai-run-options .ai-tag-list-row')
    .filter({ hasText: fixture.tag('person').name }).locator('.ai-tag-nav')

  // Mouse clicks need not leave the button focused; verify navigation and
  // card visibility instead of browser-dependent click focus behavior.
  // Previous from no selection goes to a deep, initially unmounted suggestion.
  await nav.locator('button').first().click()
  await expectNavigationAndCardVisible(nav)
  await expect(page.getByTestId('proposal-match-count')).toContainText('120 of 121 matching')

  await nav.locator('button').last().click()
  await expectNavigationAndCardVisible(nav)

  // Navigation opens Pending suggestions without hiding the tag arrows.
  await page.getByTestId('pending-suggestions-toggle').click()
  await expect(page.getByTestId('pending-suggestions-toggle')).toHaveAttribute('aria-expanded', 'false')
  await nav.locator('button').first().click()
  await expect(page.getByTestId('pending-suggestions-toggle')).toHaveAttribute('aria-expanded', 'true')
  await expectNavigationAndCardVisible(nav)

  // The alternate navigation shown when Run options are folded must work too.
  await page.getByTestId('ai-options-toggle').click()
  const foldedNav = page.getByTestId('ai-folded-nav').locator('.ai-tag-list-row')
    .filter({ hasText: fixture.tag('person').name }).locator('.ai-tag-nav')
  await foldedNav.locator('button').last().click()
  await expectNavigationAndCardVisible(foldedNav)
})
