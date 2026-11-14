import { expect, test, type Page } from '@playwright/test'
import { LONG_PASSAGE_TEXT } from '../fixtures/longPassage'
import { ensureLoggedIn, fixture, insertLongPassage, logOut, useViewport, type SearchResponse } from './support'

// The shared setup helpers (#273) from every starting state: they must reach the requested
// session and never leave another user's session behind.

const storedToken = (page: Page) => page.evaluate(() => localStorage.getItem('auth_token'))

async function signedInUsername (page: Page): Promise<string | null> {
  const token = await storedToken(page)
  if (!token) return null
  const response = await page.request.get('/api/users/me', { headers: { Authorization: `Bearer ${token}` } })
  return response.ok() ? (await response.json()).username : null
}

test('ensureLoggedIn signs in on a fresh page, keeps the right user and replaces another', async ({ page }) => {
  await ensureLoggedIn(page, 'owner') // fresh, signed-out page
  expect(await signedInUsername(page)).toBe(fixture.user('owner').username)

  const token = await storedToken(page)
  await page.reload()
  await ensureLoggedIn(page, 'owner') // already that user: the session is kept, not renewed
  expect(await storedToken(page)).toBe(token)

  await ensureLoggedIn(page, 'annotator') // another user: signed out first
  expect(await signedInUsername(page)).toBe(fixture.user('annotator').username)
  expect(await storedToken(page)).not.toBe(token)
})

test('logOut ends a session and does nothing on a signed-out page', async ({ page }) => {
  await logOut(page) // fresh page: nothing to sign out
  await ensureLoggedIn(page, 'annotator')

  await logOut(page)

  expect(await storedToken(page)).toBeNull()
  await page.getByRole('button', { name: 'User menu' }).click()
  await expect(page.locator('.q-menu').getByText('Log In', { exact: true })).toBeVisible()
})

test('a stored token the backend rejects is replaced by a new sign-in', async ({ page }) => {
  await page.goto('/')
  await page.evaluate(() => localStorage.setItem('auth_token', 'not-a-valid-token'))
  await page.reload()

  await ensureLoggedIn(page, 'owner')

  expect(await signedInUsername(page)).toBe(fixture.user('owner').username)
})

test('the helpers work on a phone, where navigation is an overlay', async ({ page }) => {
  await useViewport(page, 'phone')

  await ensureLoggedIn(page, 'owner')
  await logOut(page)

  expect(await storedToken(page)).toBeNull()
})

test('insertLongPassage replaces only its chunk\'s text and fails when the chunk is missing', () => {
  const [chronicle, gazette] = [fixture.chunk('chronicle_1'), fixture.chunk('gazette_1')]
  const body: SearchResponse = { items: [gazette, chronicle].map(({ id, text }) => ({ id, text })), ranked_ids: [], read_count: 2 }
  insertLongPassage(body)
  expect(body.items).toEqual([{ id: gazette.id, text: gazette.text }, { id: chronicle.id, text: LONG_PASSAGE_TEXT }])
  expect(() => insertLongPassage(body, 'letters_1')).toThrow('fixture letters_1 is not among the search results')
})
