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

test('a new user registers, logs in and out', async ({ page }) => {
  // The e2e profile's user database is a temporary file; a unique name keeps reruns apart.
  const name = `newcomer${Date.now()}`
  await page.goto('/')
  await page.getByRole('button', { name: 'User menu' }).click()
  await page.getByText('Register', { exact: true }).click()
  await page.getByLabel('Username').fill(name)
  await page.getByLabel('Name', { exact: true }).fill('New Comer')
  await page.getByLabel('Email').fill(`${name}@example.com`)
  await page.getByLabel('Password', { exact: true }).fill('a-long-test-password')
  await page.getByLabel('Confirm Password').fill('a-long-test-password')
  await page.getByRole('button', { name: 'Register' }).click()
  await expect(page.getByText('Account created! You can now log in.')).toBeVisible()

  await page.getByRole('button', { name: 'User menu' }).click()
  await page.getByText('Log In', { exact: true }).click()
  await page.getByLabel('Email or Username').fill(`${name}@example.com`)
  await page.getByLabel('Password', { exact: true }).fill('a-long-test-password')
  await page.getByRole('button', { name: 'Log In' }).click()
  await expect(page.getByText('Welcome, New Comer!')).toBeVisible()

  await page.getByRole('button', { name: 'User menu' }).click()
  await page.getByText('Log Out', { exact: true }).click()
  await expect(page.getByText('You have been logged out.')).toBeVisible()
})
