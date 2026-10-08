import { expect, test, type Page } from '@playwright/test'
import { fixture, logIn, openDocument } from './support'

// Shared users read and annotate a collection and may edit its tag definitions and see its
// members; membership, metadata and sharing are the owner's (ADR 0007). Read-only checks.

async function openCollectionTab (page: Page, collectionKey: string, tab: string) {
  await page.locator('.q-drawer').getByText('Collections', { exact: true }).click()
  await page.getByText(fixture.collection(collectionKey).name, { exact: true }).click()
  await page.getByText(tab, { exact: true }).click()
}

test('a shared user gets no owner-only collection controls', async ({ page }) => {
  await logIn(page, 'annotator')
  await page.locator('.q-drawer').getByText('Collections', { exact: true }).click()
  await expect(page.getByText(fixture.collection('chronicles').name, { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Share collection' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Delete collection' })).toHaveCount(0)

  await page.getByText(fixture.collection('chronicles').name, { exact: true }).click()
  await expect(page.getByRole('button', { name: 'Edit collection color' })).toBeDisabled()

  await page.getByText('Members', { exact: true }).click()
  await expect(page.getByText('@annotator')).toBeVisible() // the member list stays visible
  await expect(page.getByText('Share with a user')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Cancel share' })).toHaveCount(0)

  await page.getByText('Documents & tagging', { exact: true }).click()
  await expect(page.getByText(fixture.document('chronicle').properties.title, { exact: true })).toBeVisible()
  await expect(page.getByText('Add Document')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Remove document from collection' })).toHaveCount(0)
})

test('a shared user can still edit tag definitions', async ({ page }) => {
  await logIn(page, 'annotator')
  await openCollectionTab(page, 'chronicles', 'Tags')

  await expect(page.getByText(fixture.tag('person').name, { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Edit tag' }).first()).toBeEnabled()
})

test('a shared user annotates in the document view without membership controls', async ({ page }) => {
  await logIn(page, 'annotator')
  await openDocument(page, 'chronicles', 'chronicle')

  await expect(page.locator('.chunk-annotator').first()).toBeVisible()
  await expect(page.locator('button[title="Remove from collection"]')).toHaveCount(0)
  await expect(page.locator('button[title="Add to collection"]')).toHaveCount(0)
})

test('the owner keeps the collection controls', async ({ page }) => {
  await logIn(page, 'owner')
  await openCollectionTab(page, 'chronicles', 'Members')
  await expect(page.getByText('Share with a user')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Cancel share' })).toBeVisible()

  await page.getByText('Documents & tagging', { exact: true }).click()
  await expect(page.getByText('Add Document')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Remove document from collection' }).first()).toBeVisible()
})
