import { expect, test } from '@playwright/test'
import { annotation, chunkText, fixture, logIn, openDocument } from './support'

// Small browser smoke suite on the seeded fixture corpus. Tests only read data, so they
// share one backend; a test that mutates data must create and remove its own.

test('logged-in user stays authenticated across a reload', async ({ page }) => {
  await logIn(page, 'owner')

  await page.reload()
  await page.getByRole('button', { name: 'User menu' }).click()

  await expect(page.getByText('Log Out', { exact: true })).toBeVisible()
  await expect(page.getByText('Log In', { exact: true })).toHaveCount(0)
})

test('shared user sees the shared collection and opens its document', async ({ page }) => {
  await logIn(page, 'annotator')

  await openDocument(page, 'chronicles', 'chronicle')

  await expect(page.getByText(fixture.document('chronicle').properties.title, { exact: true })).toBeVisible()
  await expect(chunkText(page, 'chronicle_1')).toHaveText(fixture.chunk('chronicle_1').text)
  await expect(chunkText(page, 'chronicle_2')).toHaveText(fixture.chunk('chronicle_2').text)
})

test('document view renders approved annotations at their offsets', async ({ page }) => {
  await logIn(page, 'owner')

  await openDocument(page, 'chronicles', 'chronicle')

  await expect(annotation(page, 'novak_manual')).toHaveText(fixture.span('novak_manual').quote)
  await expect(annotation(page, 'brno_manual')).toHaveText(fixture.span('brno_manual').quote)
})

test('switching collection replaces the document view without stale chunks or annotations', async ({ page }) => {
  await logIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await expect(annotation(page, 'novak_manual')).toBeVisible()

  // Same document in another collection: only its chunk in that collection belongs here.
  await openDocument(page, 'newspapers', 'chronicle')

  await expect(annotation(page, 'pozar_manual')).toHaveText(fixture.span('pozar_manual').quote)
  await expect(chunkText(page, 'chronicle_1')).toHaveCount(0)
  await expect(annotation(page, 'novak_manual')).toHaveCount(0)
  await expect(page.getByText(fixture.collection('newspapers').name, { exact: true }).first()).toBeVisible()
})
