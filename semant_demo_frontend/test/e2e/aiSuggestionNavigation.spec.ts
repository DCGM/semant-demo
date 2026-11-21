import { expect, test } from '@playwright/test'
import { ensureLoggedIn, fixture, openDocument, sidebarPanelButton } from './support'

test('gutter navigation scrolls the outer sidebar to a deep virtualized suggestion (#806)', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 650 })
  const targetId = fixture.span('lhota_automatic').id
  const chunkId = fixture.chunk('chronicle_1').id

  // Add enough higher-confidence proposals to leave the real target outside the
  // QVirtualScroll slice, without writing synthetic annotations to the test database.
  await page.route('**/api/tag_spans/batch', async (route) => {
    const response = await route.fetch()
    const spans = await response.json() as Record<string, Record<string, unknown>[]>
    const target = spans[chunkId]?.find((span) => span.id === targetId)
    if (target) {
      spans[chunkId] = [
        ...spans[chunkId],
        ...Array.from({ length: 120 }, (_, i) => ({
          ...target,
          tagId: fixture.tag('person').id,
          id: `5e3a0000-0000-4000-8000-${(0xc000 + i).toString(16).padStart(12, '0')}`,
          start: 60 + (i % 12),
          end: 62 + (i % 12),
          confidence: i < 80 ? 0.99 : 0.30,
          reason: i % 3 ? `Synthetic proposal ${i}` : `Synthetic proposal ${i}: a longer explanation with additional detail on the document and the source`
        }))
      ]
    }
    await route.fulfill({ response, json: spans })
  })

  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Tagging').click()
  await expect(page.getByTestId('proposal-match-count')).toContainText('121 of 121 matching')
  await expect(page.locator(`[data-suggestion-id="${targetId}"]`)).toHaveCount(0)

  // Expanded controls push the suggestion viewport below the outer sidebar fold.
  const options = page.getByTestId('ai-run-options')
  if (!(await options.isVisible())) await page.getByTestId('ai-options-toggle').click()
  await expect(options).toBeVisible()
  await page.getByTestId('proposal-filters-toggle').click()
  await expect(page.getByTestId('proposal-tag-filter')).toBeVisible()
  const sidebar = page.locator('.q-drawer .scroll.q-px-md.q-pb-md')
    .filter({ has: page.locator('.ai-assist-panel') })
  await sidebar.evaluate((el) => { el.scrollTop = 0 })

  // The real place marker is distinct from the synthetic person suggestions.
  await page.locator(`.gutter-item.is-auto[title="${fixture.tag('place').name} (AI suggestion)"]`).click()
  const card = page.locator(`[data-suggestion-id="${targetId}"]`)
  await expect(card).toHaveClass(/is-highlighted/)
  await expect(card.getByTestId('proposal-highlight')).toBeFocused()
  await expect.poll(() => sidebar.evaluate((el) => el.scrollTop)).toBeGreaterThan(0)
  // Focus alone is insufficient: the whole card must be inside BOTH scroll viewports.
  const cardFullyVisible = () => card.evaluate((el) => {
    const outer = el.closest('.sidebar-panel')?.parentElement
    const virtualList = el.closest('.auto-span-list')
    if (!outer || !virtualList) return false
    const cardRect = el.getBoundingClientRect()
    const outerRect = outer.getBoundingClientRect()
    const listRect = virtualList.getBoundingClientRect()
    return cardRect.top >= Math.max(outerRect.top, listRect.top, 0) - 1 &&
      cardRect.bottom <= Math.min(outerRect.bottom, listRect.bottom, window.innerHeight) + 1
  })
  await expect.poll(cardFullyVisible).toBe(true)

  // Re-click the SAME annotation after manually scrolling away. Its highlighted
  // ID does not change, but the sidebar must still reveal the card again.
  await sidebar.evaluate((el) => { el.scrollTop = 0 })
  await expect.poll(cardFullyVisible).toBe(false)
  await page.locator(`.gutter-item.is-auto[title="${fixture.tag('place').name} (AI suggestion)"]`).click()
  await expect.poll(cardFullyVisible).toBe(true)
  await expect(card.getByTestId('proposal-highlight')).toBeFocused()

  // Repeat again when the card is visible but near the bottom below Run options.
  // Fitting the height leaves another part of the virtual list below the card.
  await sidebar.evaluate((el) => { el.scrollTop = 0 })
  const fittedHeight = await card.evaluate((el) => Math.ceil(el.getBoundingClientRect().bottom + 25))
  await page.setViewportSize({ width: 1280, height: fittedHeight })
  await expect.poll(cardFullyVisible).toBe(true)
  await expect.poll(() => sidebar.evaluate((el) => el.scrollHeight - el.clientHeight)).toBeGreaterThan(5)
  await page.locator(`.gutter-item.is-auto[title="${fixture.tag('place').name} (AI suggestion)"]`).click()
  await expect.poll(() => sidebar.evaluate((el) => el.scrollTop)).toBeGreaterThan(0)
  await expect.poll(cardFullyVisible).toBe(true)
  await expect(card.getByTestId('proposal-highlight')).toBeFocused()
  await expect(page.getByTestId('proposal-selection-count')).toContainText('0 / 121 visible selected')
})
