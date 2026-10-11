import { expect, test, type Page } from '@playwright/test'
import { fixture, logIn } from './support'

// Navigation follows the session (#251): Collections, Settings and Sign out for signed-in
// users, Log in and Register otherwise. The backend authorizes requests either way.

const drawer = (page: Page) => page.locator('.q-drawer--left')
const drawerItem = (page: Page, label: string) => drawer(page).locator('.drawer-item').filter({ hasText: label })

async function expectSignedOutMenu (page: Page) {
  for (const label of ['Document search', 'Chat Assistant', 'Log in', 'Register']) {
    await expect(drawerItem(page, label)).toBeVisible()
  }
  for (const label of ['Collections', 'Settings', 'Sign out']) {
    await expect(drawerItem(page, label)).toHaveCount(0)
  }
}

async function expectSignedInMenu (page: Page) {
  for (const label of ['Document search', 'Chat Assistant', 'Collections', 'Settings', 'Sign out']) {
    await expect(drawerItem(page, label)).toBeVisible()
  }
  for (const label of ['Log in', 'Register']) {
    await expect(drawerItem(page, label)).toHaveCount(0)
  }
}

test('a signed-out user sees Log in and Register, also in the collapsed drawer', async ({ page }) => {
  await page.goto('/')
  await expectSignedOutMenu(page)

  await drawer(page).getByRole('button').filter({ hasText: 'chevron_left' }).click() // collapse
  await expect(drawer(page)).toHaveClass(/q-drawer--mini/)
  await expect(drawer(page).locator('.drawer-item')).toHaveCount(5) // search, chat, about, log in, register
  await expect(drawer(page).getByText('folder', { exact: true })).toHaveCount(0) // no Collections icon

  await drawerItem(page, 'Log in').click()
  await expect(page.getByLabel('Email or Username')).toBeVisible()
})

test('logging in and signing out switch the menu without a reload', async ({ page }) => {
  await logIn(page, 'owner')
  await expectSignedInMenu(page)

  await drawerItem(page, 'Settings').click()
  await expect(page.getByText('User Information')).toBeVisible()
  await page.keyboard.press('Escape')

  await drawerItem(page, 'Collections').click()
  await expect(page.getByText(fixture.collection('chronicles').name, { exact: true })).toBeVisible()

  await drawerItem(page, 'Sign out').click()
  await expect(page.getByText('You have been logged out.')).toBeVisible()
  await expect(page).toHaveURL(/#\/search/) // left the protected page
  await expect(page.getByText(fixture.collection('chronicles').name, { exact: true })).toHaveCount(0)
  await expectSignedOutMenu(page)
})

test('a signed-out direct link to a collection page goes to search', async ({ page }) => {
  await page.goto(`/#/collections/${fixture.collection('chronicles').id}/overview`)

  await expect(page).toHaveURL(/#\/search/)
  await expect(page.getByText('Log in to open your collections.')).toBeVisible()
  await expect(page.getByText(fixture.collection('chronicles').name, { exact: true })).toHaveCount(0)
})

test('a restored session opens a direct link to a collection page', async ({ page }) => {
  await logIn(page, 'owner')

  await page.goto(`/#/collections/${fixture.collection('chronicles').id}/overview`)
  await page.reload()

  await expect(page).toHaveURL(/\/overview$/)
  await expect(page.getByText(fixture.collection('chronicles').name, { exact: true }).first()).toBeVisible()
  await expectSignedInMenu(page)
})

test('an expired session on a collection page switches to the signed-out menu', async ({ page }) => {
  await logIn(page, 'owner')
  // The backend rejects the token from now on, as it does once a token expires.
  await page.route('**/api/user_collections', (route) => route.fulfill({
    status: 401, contentType: 'application/json', body: '{"detail":"Unauthorized"}'
  }))

  await drawerItem(page, 'Collections').click()

  await expect(page.getByText('Your session has expired. Please log in again.')).toBeVisible()
  await expect(page).toHaveURL(/#\/search/)
  await expectSignedOutMenu(page)
})

test('a stored session that is no longer valid restores as signed out', async ({ page }) => {
  await logIn(page, 'owner')
  await page.route('**/api/users/me', (route) => route.fulfill({
    status: 401, contentType: 'application/json', body: '{"detail":"Unauthorized"}'
  }))

  await page.reload()

  await expectSignedOutMenu(page)
})
