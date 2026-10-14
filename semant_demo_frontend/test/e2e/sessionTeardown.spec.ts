import { expect, test, type Page, type Route } from '@playwright/test'
import { ensureLoggedIn, fixture, logOut } from './support'

// #267: ending or switching a session removes the old user's UI, in this tab and in every
// other open tab of the app (they share localStorage), without a reload.

const drawerItem = (page: Page, label: string) => page.locator('.q-drawer--left .drawer-item').filter({ hasText: label })
const ownCollection = fixture.collection('chronicles').name

/** A token for `userKey`, issued by the backend without touching any open page. */
async function tokenOf (page: Page, userKey: string): Promise<string> {
  const user = fixture.user(userKey)
  const response = await page.request.post('/api/auth/jwt/login', { form: { username: user.username, password: user.password } })
  expect(response.ok(), `login answered ${response.status()}`).toBe(true)
  return (await response.json()).access_token
}

/** A second tab of the same browser, on the owner's collection list. */
async function secondTabOnCollections (page: Page): Promise<Page> {
  const other = await page.context().newPage()
  await other.goto('/#/collections')
  await expect(other.getByText(ownCollection, { exact: true })).toBeVisible()
  return other
}

test('signing out in one tab leaves the protected page and its data in another', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await page.evaluate(() => localStorage.setItem('collections.viewMode', 'list'))
  const other = await secondTabOnCollections(page)

  await logOut(page)

  await expect(other.getByText('You signed out in another tab.')).toBeVisible()
  await expect(other).toHaveURL(/#\/search/)
  await expect(other.getByText(ownCollection, { exact: true })).toHaveCount(0)
  await expect(drawerItem(other, 'Log in')).toBeVisible()
  await expect(drawerItem(other, 'Collections')).toHaveCount(0)
  expect(await other.evaluate(() => localStorage.getItem('collections.viewMode'))).toBe('list')
})

test('an account switch in one tab never shows the previous user\'s collections in another', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  const other = await secondTabOnCollections(page)

  // The first tab now stores another account's token (signed in as someone else).
  const outsiderToken = await tokenOf(page, 'outsider')
  await page.evaluate((token) => localStorage.setItem('auth_token', token), outsiderToken)

  await expect(other.getByText('Your session changed in another tab.')).toBeVisible()
  await expect(other.getByText(ownCollection, { exact: true })).toHaveCount(0)
  await drawerItem(other, 'Collections').click()
  await expect(other.getByText(fixture.collection('outsider_notes').name, { exact: true })).toBeVisible()
  await expect(other.getByText(ownCollection, { exact: true })).toHaveCount(0)
})

test('signing out in another tab closes an open account dialog', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  const other = await page.context().newPage()
  await other.goto('/#/search')
  await drawerItem(other, 'Settings').click()
  await expect(other.getByText('User Information')).toBeVisible()
  await other.getByLabel('New Password', { exact: true }).fill('draft-password')

  await logOut(page)

  await expect(other.getByText('User Information')).toHaveCount(0)
  await expect(drawerItem(other, 'Settings')).toHaveCount(0)
})

test('a chat answer still on its way after sign-out does not appear', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  let held: Route | null = null
  await page.route('**/api/rag', (route) => { held = route })
  await page.goto('/#/rag')
  await page.getByPlaceholder('Vaše otázka?').fill('A question asked before signing out')
  await page.getByPlaceholder('Vaše otázka?').press('Enter')
  await expect(page.getByText('A question asked before signing out')).toBeVisible()
  await expect.poll(() => held !== null).toBe(true)

  await logOut(page)
  await (held as unknown as Route).fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ rag_answer: 'Answer for the signed-out user', sources: [], response_id: 'r1', time_spent: 1 })
  })

  await expect(page.getByText('A question asked before signing out')).toHaveCount(0)
  await expect(page.getByText('Answer for the signed-out user')).toHaveCount(0)
  await expect(page.getByText('Ahoj, máte na mě nějakou otázku?')).toBeVisible()
})

test('a failed server logout still signs out here and says so', async ({ page }) => {
  const pageErrors: Error[] = []
  page.on('pageerror', (error) => pageErrors.push(error))
  await ensureLoggedIn(page, 'owner')
  await page.route('**/api/auth/jwt/logout', (route) => route.abort('internetdisconnected'))

  await drawerItem(page, 'Sign out').click()

  await expect(page.getByText('You have been logged out on this device, but the server could not confirm the sign-out.')).toBeVisible()
  await expect(drawerItem(page, 'Log in')).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('auth_token'))).toBeNull()
  expect(pageErrors).toEqual([])
})

test('signing out in another tab while an explanation is open closes it without errors', async ({ page }) => {
  const pageErrors: Error[] = []
  page.on('pageerror', (error) => pageErrors.push(error))
  await ensureLoggedIn(page, 'owner')
  await page.route('**/api/rag', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      rag_answer: 'An answer worth explaining in detail [doc 1].',
      sources: [{ id: 'c1', text: 'Source text', start_page_id: 'p1', from_page: 1, to_page: 1, document: 'd1', order: 0, document_object: { id: 'd1' } }],
      response_id: 'r1',
      time_spent: 1
    })
  }))
  await page.route('**/api/rag/explain', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ explanation: 'The explanation of the claim.' })
  }))
  await page.goto('/#/rag')
  await page.getByPlaceholder('Vaše otázka?').fill('Question')
  await page.getByPlaceholder('Vaše otázka?').press('Enter')
  const answer = page.locator('.markdown-body').filter({ hasText: 'An answer worth explaining' })
  await answer.selectText()
  await answer.dispatchEvent('mouseup')
  await page.getByRole('button', { name: 'Explain' }).click()
  await expect(page.getByText('The explanation of the claim.')).toBeVisible()

  const other = await page.context().newPage()
  await other.goto('/#/search')
  await logOut(other)

  await expect(page.getByText('The explanation of the claim.')).toHaveCount(0)
  await expect(page.getByText('An answer worth explaining')).toHaveCount(0)
  expect(pageErrors).toEqual([])
})
