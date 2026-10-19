import { expect, test, type Page } from '@playwright/test'
import { ensureLoggedIn, fixture, useViewport } from './support'

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

  await drawer(page).getByRole('button', { name: 'Collapse navigation' }).click()
  await expect(drawer(page)).toHaveClass(/q-drawer--mini/)
  await expect(drawer(page).locator('.drawer-item')).toHaveCount(6) // search, chat, corpus, about, log in, register
  await expect(drawer(page).getByText('folder', { exact: true })).toHaveCount(0) // no Collections icon

  await drawerItem(page, 'Log in').click()
  await expect(page.getByLabel('Email or Username')).toBeVisible()
})

test('logging in and signing out switch the menu without a reload', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
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
  await ensureLoggedIn(page, 'owner')

  await page.goto(`/#/collections/${fixture.collection('chronicles').id}/overview`)
  await page.reload()

  await expect(page).toHaveURL(/\/overview$/)
  await expect(page.getByText(fixture.collection('chronicles').name, { exact: true }).first()).toBeVisible()
  await expectSignedInMenu(page)
})

test('an expired session on a collection page switches to the signed-out menu', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
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
  await ensureLoggedIn(page, 'owner')
  await page.route('**/api/users/me', (route) => route.fulfill({
    status: 401, contentType: 'application/json', body: '{"detail":"Unauthorized"}'
  }))

  await page.reload()

  await expectSignedOutMenu(page)
})

// #253: back arrows go to a fixed parent page and leave the left navigation drawer alone;
// the drawer's own collapse control is a separate, labelled toggle.
test('back arrows go to the parent page without changing the navigation drawer', async ({ page }) => {
  const collection = fixture.collection('chronicles')
  const document = fixture.document('chronicle')
  await ensureLoggedIn(page, 'owner')

  await drawer(page).getByRole('button', { name: 'Collapse navigation' }).click()
  await expect(drawer(page)).toHaveClass(/q-drawer--mini/)

  // Direct link to the document view: no in-app history, back still goes to the collection.
  await page.goto(`/#/collections/${collection.id}/documents/${document.id}`)
  await expect(page.getByText('Document detail')).toBeVisible()
  await page.getByRole('link', { name: 'Back to collection documents' }).click()
  await expect(page).toHaveURL(new RegExp(`#/collections/${collection.id}/documents$`))
  await expect(drawer(page)).toHaveClass(/q-drawer--mini/)

  await drawer(page).getByRole('button', { name: 'Expand navigation' }).click()
  await expect(drawer(page)).not.toHaveClass(/q-drawer--mini/)
  await page.getByRole('link', { name: 'Back to collections' }).click()
  await expect(page).toHaveURL(/#\/collections$/)
  await expect(drawer(page)).toBeVisible()
  await expect(drawer(page)).not.toHaveClass(/q-drawer--mini/)

  // Top-level pages have no back arrow.
  await expect(page.getByRole('link', { name: /^Back to/ })).toHaveCount(0)
  await drawerItem(page, 'Document search').click()
  await expect(page.getByRole('link', { name: /^Back to/ })).toHaveCount(0)
})

// #271: below the breakpoint the navigation is an overlay that starts closed on first load.
test('on a phone, the navigation starts closed on first load and opens from the header', async ({ page }) => {
  await useViewport(page, 'phone')
  await page.goto('/#/search')
  await expect(page.getByRole('button', { name: 'User menu' })).toBeVisible() // the layout has mounted

  const showNavigation = page.getByRole('button', { name: 'Show navigation' })
  await expect(showNavigation).toHaveAttribute('aria-expanded', 'false')
  await expect(drawer(page)).toBeHidden()
  await expect(page.locator('.q-drawer__backdrop:not(.hidden)')).toHaveCount(0)

  await showNavigation.click()
  await expect(drawer(page)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Hide navigation' })).toHaveAttribute('aria-expanded', 'true')
  await expect(drawerItem(page, 'Document search')).toBeInViewport()
})

test('on a phone, back arrows navigate and leave the overlay navigation closed', async ({ page }) => {
  const collection = fixture.collection('chronicles')
  await ensureLoggedIn(page, 'owner')
  await useViewport(page, 'phone')

  await page.goto(`/#/collections/${collection.id}/documents/${fixture.document('chronicle').id}`)
  await expect(page.getByText('Document detail')).toBeVisible()
  await expect(drawer(page)).toBeHidden()
  await expect(page.getByRole('button', { name: /^(Collapse|Expand) navigation$/ })).toHaveCount(0)

  await page.getByRole('link', { name: 'Back to collection documents' }).click()
  await expect(page).toHaveURL(new RegExp(`#/collections/${collection.id}/documents$`))
  await page.getByRole('link', { name: 'Back to collections' }).click()
  await expect(page).toHaveURL(/#\/collections$/)
  await expect(drawer(page)).toBeHidden()

  await page.getByRole('button', { name: 'Show navigation' }).click()
  await expect(drawer(page)).toBeVisible()
})
