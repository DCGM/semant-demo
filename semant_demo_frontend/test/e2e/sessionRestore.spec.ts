import { expect, test, type Page } from '@playwright/test'
import { ensureLoggedIn, fixture } from './support'

// #319 (first part): a stored session survives a page load while the backend is unreachable
// or failing; only a rejected token ends it.

const drawerItem = (page: Page, label: string) => page.locator('.q-drawer--left .drawer-item').filter({ hasText: label })
const restoreNotice = (page: Page) => page.getByText('Could not restore your session: the server is unreachable or failing.')
const ownCollection = fixture.collection('chronicles').name

test('a server error on reload keeps the session, and Retry restores it', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  const token = await page.evaluate(() => localStorage.getItem('auth_token'))
  await page.route('**/api/users/me', (route) => route.fulfill({ status: 503, body: 'Service Unavailable' }))

  await page.goto('about:blank') // a real page load (a hash change alone keeps the app running)
  await page.goto('/#/collections')

  await expect(restoreNotice(page)).toBeVisible()
  await expect(page).toHaveURL(/#\/search/)
  await expect(page.getByText('Log in to open your collections.')).toHaveCount(0)
  await expect(drawerItem(page, 'Collections')).toHaveCount(0)
  expect(await page.evaluate(() => localStorage.getItem('auth_token'))).toBe(token)

  await page.unroute('**/api/users/me')
  await page.getByRole('button', { name: 'Retry' }).click()

  await expect(drawerItem(page, 'Collections')).toBeVisible()
  await expect(restoreNotice(page)).toHaveCount(0)
  await drawerItem(page, 'Collections').click()
  await expect(page.getByText(ownCollection, { exact: true })).toBeVisible()
})

test('an unreachable server on reload keeps the session until the browser is back online', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await page.route('**/api/users/me', (route) => route.abort('internetdisconnected'))

  await page.reload()

  await expect(restoreNotice(page)).toBeVisible()
  await expect(drawerItem(page, 'Log in')).toBeVisible()

  await page.unroute('**/api/users/me')
  await page.evaluate(() => window.dispatchEvent(new Event('online')))

  await expect(drawerItem(page, 'Sign out')).toBeVisible()
  await expect(restoreNotice(page)).toHaveCount(0)
})

test('a rejected token on reload still ends the session', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await page.route('**/api/users/me', (route) => route.fulfill({ status: 401, json: { detail: 'Unauthorized' } }))

  await page.reload()

  await expect(drawerItem(page, 'Log in')).toBeVisible()
  await expect.poll(() => page.evaluate(() => localStorage.getItem('auth_token'))).toBeNull()
  await expect(restoreNotice(page)).toHaveCount(0)
})
