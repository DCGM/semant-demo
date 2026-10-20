import { expect, test, type Page, type Request } from '@playwright/test'

import {
  answerChat, answerGuestQuota, chatSource, closePhoneNavigation, editSearchResults, ensureLoggedIn, logOut, search, useViewport
} from './support'

// The daily AI allowance in the browser (#234). The first two tests use the real backend
// profile: its guest cookie and its allowance. The others answer `/api/quota`, `/api/rag`
// or `/api/search` themselves to reach the near-limit and exhausted states, which the
// profile's cheap fake calls would take hundreds of operations to reach.

const indicator = (page: Page) => page.getByRole('button', { name: /^AI allowance: \d+% left today$/ })
const details = (page: Page) => page.getByTestId('quota-details')
const banner = (page: Page) => page.getByTestId('quota-banner')

/** Opens the allowance menu in the header. */
async function openDetails (page: Page) {
  await indicator(page).click()
  await expect(details(page)).toBeVisible()
}

/**
 * The same build on a second origin, `http://127.0.0.1:<port + 2>`, served by the profile
 * (`tests/e2e_server.py`), which allows its credentialed requests: its API requests cross
 * origins, as in local development (frontend :9000, API :8000).
 */
const secondOrigin = (baseURL: string) => `http://127.0.0.1:${Number(new URL(baseURL).port) + 2}`

const guestCookie = (header: string | undefined) => header?.match(/(?:^|;\s*)semant_guest=([^;]+)/)?.[1] ?? null

test('a guest of a frontend on another origin keeps one guest cookie, and its AI use counts', async ({ page, baseURL }) => {
  await useViewport(page, 'wide')
  // API requests started after the guest cookie was issued.
  const laterRequests: Request[] = []
  const issued: string[] = []
  const statuses: Promise<{ principal: string, used_usd: number }>[] = []
  page.on('request', (request) => {
    if (request.url().startsWith(`${baseURL}/api/`) && issued.length) laterRequests.push(request)
  })
  page.on('response', async (response) => {
    if (!response.url().startsWith(`${baseURL}/api/`)) return
    if (response.url() === `${baseURL}/api/quota`) statuses.push(response.json())
    const cookie = guestCookie((await response.headerValue('set-cookie')) ?? undefined)
    if (cookie) issued.push(cookie)
  })

  await page.goto(`${secondOrigin(baseURL!)}/#/search`)
  await closePhoneNavigation(page)
  await expect(indicator(page)).toHaveAccessibleName('AI allowance: 100% left today')
  await page.getByRole('textbox').first().fill('Lhota')
  await page.keyboard.press('Enter')
  await expect(page.locator('#result-1')).toBeVisible()

  // The path only: the request carries the length level as a query parameter (#360).
  const summary = page.waitForResponse((r) => r.url().split('?')[0] === `${baseURL}/api/summarize/results`)
  await page.getByRole('button', { name: 'Summarize Results' }).click()
  expect((await summary).status()).toBe(200)
  // The allowance is read again after the AI operation.
  await expect.poll(async () => (await statuses.at(-1))?.used_usd ?? 0).toBeGreaterThan(0)
  const used = (await statuses.at(-1))!

  // The summary was charged to the guest whose allowance the page then read.
  expect(used.principal).toBe('guest')
  expect(used.used_usd).toBeGreaterThan(0)
  // One guest: issued once, then sent with every later request (search, summary, allowance).
  expect(issued).toHaveLength(1)
  const sent = await Promise.all(laterRequests.map(async (r) => guestCookie(await r.headerValue('cookie') ?? undefined)))
  expect(laterRequests.map((r) => new URL(r.url()).pathname)).toEqual(expect.arrayContaining(['/api/search', '/api/summarize/results']))
  expect(sent).toEqual(sent.map(() => issued[0]))
  // And it is kept: the reloaded page shows the same guest's allowance.
  const reloaded = page.waitForResponse(`${baseURL}/api/quota`)
  await page.reload()
  expect((await (await reloaded).json() as { used_usd: number }).used_usd).toBe(used.used_usd)
  expect(issued).toHaveLength(1)
})

test('a signed-in user sees the account allowance, and after signing out the guest one', async ({ page }) => {
  await useViewport(page, 'wide')
  await ensureLoggedIn(page, 'annotator')
  await openDetails(page)
  await expect(details(page)).toContainText('Your account\'s allowance.')
  await expect(details(page).getByRole('button', { name: 'Register' })).toHaveCount(0)
  await page.keyboard.press('Escape')

  await logOut(page)
  await openDetails(page)
  await expect(details(page)).toContainText('Guest allowance of this browser.')
  await expect(details(page).getByRole('button', { name: 'Log in' })).toBeVisible()
})

test('a guest near the limit is warned, with Log in and Register', async ({ page }) => {
  await useViewport(page, 'narrow')
  await answerGuestQuota(page, 0.21)
  await page.goto('/#/rag')
  await closePhoneNavigation(page)

  await expect(banner(page)).toContainText('You have used 84% of today\'s AI allowance. It resets')
  await expect(indicator(page)).toHaveAccessibleName('AI allowance: 16% left today')
  await banner(page).getByRole('button', { name: 'Log in' }).click()
  const login = page.getByRole('dialog')
  await expect(login.getByLabel('Email or Username')).toBeVisible()
  await login.locator('.q-btn', { hasText: 'close' }).click() // an icon button without a name
  await expect(login).toHaveCount(0)

  await banner(page).getByRole('button', { name: 'Dismiss' }).click()
  await expect(banner(page)).toHaveCount(0)
})

test('an exhausted guest is told why a chat question was refused, and it is not retried', async ({ page }) => {
  await useViewport(page, 'phone')
  const reset = await answerGuestQuota(page, 0.25)
  await answerChat(page, [{ rag_answer: 'unused', sources: [chatSource('chronicle_1')] }])
  let asked = 0
  await page.route('**/api/rag', (route) => {
    asked++
    return route.fulfill({
      status: 429,
      headers: { 'Retry-After': '3600' },
      json: {
        detail: 'Insufficient remaining daily AI allowance for this operation; it resets at … UTC.',
        code: 'llm_quota_exhausted',
        principal: 'guest',
        reset_at: reset.toISOString(),
        limit_usd: 0.25,
        used_usd: 0.25
      }
    })
  })
  await page.goto('/#/rag')
  await closePhoneNavigation(page)
  await expect(banner(page)).toContainText('Today\'s AI allowance is used up.')

  const input = page.getByPlaceholder('Vaše otázka?')
  await input.fill('What happened in Lhota?')
  await input.press('Enter')

  await expect(page.locator('.message-bubble').last()).toContainText(
    'Today\'s AI allowance has no room for this request, so nothing was generated.')
  await expect(page.locator('.message-bubble').last()).toContainText('Logging in gives you a separate daily allowance.')
  await expect(input).toBeEnabled()
  expect(asked).toBe(1)
})

test('Search keeps its results and says why AI titles and summaries were skipped', async ({ page }) => {
  await useViewport(page, 'wide')
  const reset = await answerGuestQuota(page, 0.25)
  const detail = 'Insufficient remaining daily AI allowance for this operation; it resets at … UTC.'
  await editSearchResults(page, (body) => {
    Object.assign(body, {
      warnings: [`Titles and summaries were not generated. ${detail}`],
      quota_exhausted: {
        detail, code: 'llm_quota_exhausted', principal: 'guest', reset_at: reset.toISOString(), limit_usd: 0.25, used_usd: 0.25
      }
    })
  })

  await search(page, 'Lhota')

  await expect(page.locator('#result-1')).toBeVisible()
  await expect(page.getByText('AI titles and summaries were skipped: today\'s AI allowance has no room for them.')).toBeVisible()
  await expect(page.getByText('Titles and summaries were not generated.')).toHaveCount(0)
})
