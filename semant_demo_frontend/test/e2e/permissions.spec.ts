import { expect, test, type Page } from '@playwright/test'
import { ensureLoggedIn, fixture, openDocument } from './support'

// Shared users read and annotate a collection and may edit its tag definitions and see its
// members; membership, metadata and sharing are the owner's (ADR 0007). Read-only checks.

// A click that lands on something covering the tab (e.g. the tabs' scroll arrow, #489) fails
// here, at the click, rather than as missing page content.
async function clickCollectionTab (page: Page, tab: string) {
  const routeTab = page.getByRole('tab', { name: tab, exact: true })
  await routeTab.click()
  await expect(routeTab, `the ${tab} tab did not open`).toHaveAttribute('aria-selected', 'true')
}

// Waits for the collection's name in the header, which loads after the route.
async function openCollection (page: Page, collectionKey: string) {
  const name = fixture.collection(collectionKey).name
  await page.getByText(name, { exact: true }).click()
  await expect(page.locator('.collection-page-title')).toHaveText(name)
}

async function openCollectionTab (page: Page, collectionKey: string, tab: string) {
  await page.locator('.q-drawer').getByText('Collections', { exact: true }).click()
  await openCollection(page, collectionKey)
  await clickCollectionTab(page, tab)
}

test('a shared user gets no owner-only collection controls', async ({ page }) => {
  await ensureLoggedIn(page, 'annotator')
  await page.locator('.q-drawer').getByText('Collections', { exact: true }).click()
  await expect(page.getByText(fixture.collection('chronicles').name, { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Share collection' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Delete collection' })).toHaveCount(0)

  await openCollection(page, 'chronicles')
  await expect(page.getByRole('button', { name: 'Edit collection color' })).toBeDisabled()

  await clickCollectionTab(page, 'Members')
  await expect(page.getByText('@annotator')).toBeVisible() // the member list stays visible
  await expect(page.getByText('Share with a user')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Cancel share' })).toHaveCount(0)

  await clickCollectionTab(page, 'Documents & tagging')
  await expect(page.getByText(fixture.document('chronicle').properties.title, { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Add from Library' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Remove document from collection' })).toHaveCount(0)
})

test('a shared user can still edit tag definitions', async ({ page }) => {
  await ensureLoggedIn(page, 'annotator')
  await openCollectionTab(page, 'chronicles', 'Tags')

  await expect(page.getByText(fixture.tag('person').name, { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Edit tag' }).first()).toBeEnabled()
})

test('a shared user annotates in the document view without membership controls', async ({ page }) => {
  await ensureLoggedIn(page, 'annotator')
  await openDocument(page, 'chronicles', 'chronicle')

  await expect(page.locator('.chunk-annotator').first()).toBeVisible()
  await expect(page.locator('button[title="Remove from collection"]')).toHaveCount(0)
  await expect(page.locator('button[title="Add to collection"]')).toHaveCount(0)
})

test('the owner keeps the collection controls', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openCollectionTab(page, 'chronicles', 'Members')
  await expect(page.getByText('Share with a user')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Cancel share' })).toBeVisible()

  await clickCollectionTab(page, 'Documents & tagging')
  await expect(page.getByRole('button', { name: 'Add from Library' })).toBeVisible()
  await expect(page.getByText(/Create New Document|Upload Document/)).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Remove document from collection' }).first()).toBeVisible()
})
