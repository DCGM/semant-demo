import { expect, test, type Page } from '@playwright/test'
import { ensureLoggedIn, fixture, logOut } from './support'

// #319 (first part): availability is not authentication. A stored session survives a page
// load while the backend is unreachable or failing (awaiting verification, never shown as
// signed out); a verified session survives failing requests; only a rejected token ends it.

const drawerItem = (page: Page, label: string) => page.locator('.q-drawer--left .drawer-item').filter({ hasText: label })
const banner = (page: Page) => page.locator('.session-banner')
const ownCollection = fixture.collection('chronicles').name
const storedToken = (page: Page) => page.evaluate(() => localStorage.getItem('auth_token'))

/** Neither signed in nor signed out: Sign out only, no user pages, no Log in / Register. */
async function expectAwaitingVerification (page: Page): Promise<void> {
  await expect(banner(page)).toContainText('Your previous sign-in is stored on this device')
  await expect(drawerItem(page, 'Sign out')).toBeVisible()
  for (const label of ['Log in', 'Register', 'Collections', 'Settings']) await expect(drawerItem(page, label)).toHaveCount(0)
}

test('a direct link during a server error waits for verification and opens after Retry', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  const token = await storedToken(page)
  await page.route('**/api/users/me', (route) => route.fulfill({ status: 503, body: 'Service Unavailable' }))

  await page.goto('about:blank') // a real page load (a hash change alone keeps the app running)
  await page.goto('/#/collections')

  await expect(page).toHaveURL(/#\/session-pending\?redirect=\/collections$/)
  await expect(page.getByText('Waiting to verify your session')).toBeVisible()
  await expectAwaitingVerification(page)
  await expect(page.getByText('Log in to open your collections.')).toHaveCount(0)
  await expect(page.getByText(ownCollection, { exact: true })).toHaveCount(0)
  expect(await storedToken(page)).toBe(token)

  await banner(page).getByRole('button', { name: 'Retry' }).click()
  await expectAwaitingVerification(page) // still failing

  await page.unroute('**/api/users/me')
  await banner(page).getByRole('button', { name: 'Retry' }).click()

  await expect(page).toHaveURL(/#\/collections$/)
  await expect(page.getByText(ownCollection, { exact: true })).toBeVisible()
  await expect(banner(page)).toHaveCount(0)
  await expect(drawerItem(page, 'Collections')).toBeVisible()
})

test('Sign out works while the server is unreachable', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await page.route('**/api/**', (route) => route.abort('internetdisconnected'))
  const logoutRequests: string[] = []
  page.on('request', (request) => { if (request.url().includes('/api/auth/jwt/logout')) logoutRequests.push(request.url()) })

  await page.reload()
  await expectAwaitingVerification(page)
  await banner(page).getByRole('button', { name: 'Sign out' }).click()

  await expect(page.getByText('You have been logged out.')).toBeVisible()
  await expect(drawerItem(page, 'Log in')).toBeVisible()
  await expect(banner(page)).toHaveCount(0)
  expect(await storedToken(page)).toBeNull()
  expect(logoutRequests).toEqual([])
})

test('verification is retried when the browser is back online', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await page.route('**/api/users/me', (route) => route.abort('internetdisconnected'))

  await page.reload()
  await expectAwaitingVerification(page)

  await page.unroute('**/api/users/me')
  await page.evaluate(() => window.dispatchEvent(new Event('online')))

  await expect(drawerItem(page, 'Collections')).toBeVisible()
  await expect(banner(page)).toHaveCount(0)
})

test('a verified session stays signed in and on its page when requests fail', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await drawerItem(page, 'Collections').click()
  await expect(page.getByText(ownCollection, { exact: true })).toBeVisible()
  const token = await storedToken(page)
  await page.route('**/api/**', (route) => route.request().url().includes('/api/users/')
    ? route.continue()
    : route.fulfill({ status: 503, body: 'Service Unavailable' }))

  await drawerItem(page, 'Document search').click()
  await drawerItem(page, 'Collections').click()
  await expect(page).toHaveURL(/#\/collections$/)
  await page.unroute('**/api/**')
  await page.route('**/api/**', (route) => route.abort('internetdisconnected'))
  await drawerItem(page, 'Document search').click()
  await drawerItem(page, 'Collections').click()

  await expect(page).toHaveURL(/#\/collections$/)
  await expect(drawerItem(page, 'Sign out')).toBeVisible()
  await expect(drawerItem(page, 'Log in')).toHaveCount(0)
  await expect(banner(page)).toHaveCount(0)
  expect(await storedToken(page)).toBe(token)
})

test('signing out in another tab ends a session that awaits verification', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  const other = await page.context().newPage()
  await other.route('**/api/users/me', (route) => route.fulfill({ status: 503, body: 'Service Unavailable' }))
  await other.goto('/#/collections')
  await expect(other).toHaveURL(/#\/session-pending/)

  await logOut(page)

  await expect(other).toHaveURL(/#\/search/)
  await expect(drawerItem(other, 'Log in')).toBeVisible()
  await expect(banner(other)).toHaveCount(0)
})

test('a rejected token on reload still ends the session', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await page.route('**/api/users/me', (route) => route.fulfill({ status: 401, json: { detail: 'Unauthorized' } }))

  await page.reload()

  await expect(drawerItem(page, 'Log in')).toBeVisible()
  await expect.poll(() => storedToken(page)).toBeNull()
  await expect(banner(page)).toHaveCount(0)
})
