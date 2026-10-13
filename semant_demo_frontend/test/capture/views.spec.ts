import { expect, test, type Page, type TestInfo } from '@playwright/test'
import { annotation, fixture, logIn } from '../e2e/support'

// UI review captures (`scripts/e2e-dev.sh capture`), not part of `make test-e2e`. The
// capture projects in playwright.config.ts run this file at wide desktop, narrow desktop
// and phone widths; each view is saved as test-results/ui-capture/<view>-<project>.png.
// At the narrow desktop width both sidebars must be open, as reviewed in #256/#272.

async function save (page: Page, testInfo: TestInfo, view: string) {
  const file = `${testInfo.project.outputDir}/ui-capture/${view}-${testInfo.project.name}.png`
  // The viewport as a user sees it (a full-page shot cuts the fixed sidebars off).
  await page.screenshot({ path: file })
}

/** Logs in at desktop width (the phone navigation overlay covers the user menu). */
async function logInAsOwner (page: Page) {
  const viewport = page.viewportSize()!
  await page.setViewportSize({ width: 1280, height: 900 })
  await logIn(page, 'owner')
  await page.setViewportSize(viewport)
}

/** On a phone the navigation starts open as an overlay; tap beside it to close it. */
async function closePhoneNavigation (page: Page) {
  const viewport = page.viewportSize()
  if (!viewport || viewport.width >= 600) return
  const backdrop = page.locator('.q-drawer__backdrop:not(.hidden)')
  await backdrop.first().click({ position: { x: viewport.width - 20, y: viewport.height / 2 } })
  await expect(backdrop).toHaveCount(0)
  await expect(page.locator('.q-drawer--left')).not.toBeInViewport() // slid out, not mid-animation
}

async function expectSidebarsOpen (page: Page, testInfo: TestInfo) {
  if (testInfo.project.name !== 'narrow') return
  await expect(page.locator('.q-drawer--left')).toBeVisible()
  await expect(page.locator('.q-drawer--left')).not.toHaveClass(/q-drawer--mini/)
  await expect(page.locator('.q-drawer--right')).toBeVisible()
  await expect(page.locator('.q-drawer--right')).not.toHaveClass(/q-drawer--mini/)
}

test('search results', async ({ page }, testInfo) => {
  await logInAsOwner(page)
  await page.goto('/#/search')
  await page.reload() // lay the page out at the project's width from the start
  await page.getByRole('textbox').first().fill('Lhota')
  await page.keyboard.press('Enter')
  await expect(page.locator('#result-1')).toBeVisible()
  await closePhoneNavigation(page)
  await expectSidebarsOpen(page, testInfo)
  await save(page, testInfo, 'search-results')
})

test('document view', async ({ page }, testInfo) => {
  await logInAsOwner(page)
  await page.goto(`/#/collections/${fixture.collection('chronicles').id}/documents/${fixture.document('chronicle').id}`)
  await page.reload()
  await expect(annotation(page, 'novak_manual')).toBeVisible()
  await expect(page.locator('.gutter-item')).toHaveCount(2)
  await closePhoneNavigation(page)
  await expectSidebarsOpen(page, testInfo)
  await save(page, testInfo, 'document-view')
})
