import { expect, type APIRequestContext, type Locator, type Page } from '@playwright/test'
import { viewports, type ViewportName } from './viewports'
// Same synthetic corpus the backend profile seeds (single source, shared with pytest).
import corpus from '../../../semant_demo_backend/tests/fixtures/corpus.json'

type Keyed = { key: string }

function byKey<T extends Keyed> (items: T[], key: string): T {
  const item = items.find((i) => i.key === key)
  if (!item) throw new Error(`fixture ${key} not found`)
  return item
}

export const fixture = {
  user: (key: string) => byKey(corpus.users, key),
  collection: (key: string) => byKey(corpus.collections, key),
  document: (key: string) => byKey(corpus.documents, key),
  chunk: (key: string) => byKey(corpus.documents.flatMap((d) => d.chunks), key),
  span: (key: string) => byKey(corpus.spans, key),
  tag: (key: string) => byKey(corpus.tags, key)
}

// Conventions for the helpers below:
// - Every test sets up its own state (viewport, session, search); none relies on another
//   test or on test order. Helpers are idempotent: call them from any starting state.
// - They act through the UI as a user would and wait on visible state, never on sleeps,
//   retries or `force` clicks; a missing control fails with a message naming it.
// - Use them for setup. Keep the behavior a test is about spelled out in the test.
//
//   await useViewport(page, 'phone')
//   await ensureLoggedIn(page, 'annotator')   // signed out, already annotator, or owner
//   await search(page, 'Lhota')
//   await goToResultsPage(page, 2)

export { viewports, type ViewportName } from './viewports'

/** Resizes the page to one of the reviewed layouts; call it before `page.goto` or a helper. */
export async function useViewport (page: Page, name: ViewportName): Promise<void> {
  await page.setViewportSize(viewports[name])
}

const userMenu = (page: Page) => page.getByRole('button', { name: 'User menu' })

/** Opens the app unless the page already shows it, and waits for the layout. */
async function openApp (page: Page): Promise<void> {
  if (!page.url().startsWith('http')) await page.goto('/')
  await expect(userMenu(page), 'the app layout (User menu) did not render').toBeVisible()
  await closePhoneNavigation(page)
}

/**
 * Workaround for #271 in one place; delete it with the fix. On a phone the navigation
 * drawer opens as an overlay when the app loads (a route change closes it) and covers the
 * header. Taps beside it, as a user would. The drawer state is set when the layout mounts,
 * so after the User menu has rendered it is known.
 */
export async function closePhoneNavigation (page: Page): Promise<void> {
  const viewport = page.viewportSize()
  await expect(userMenu(page)).toBeVisible()
  if (!viewport || viewport.width >= 1024) return // drawers are overlays below Quasar's breakpoint
  const backdrop = page.locator('.q-drawer__backdrop:not(.hidden)')
  if (await backdrop.count() === 0) return
  await backdrop.first().click({ position: { x: viewport.width - 20, y: viewport.height / 2 } })
  await expect(backdrop).toHaveCount(0)
  await expect(page.locator('.q-drawer--left')).not.toBeInViewport() // slid out, not mid-animation
}

/** The user of the token the page stores, or null when it stores none or a rejected one. */
async function storedUser (page: Page): Promise<{ username: string } | null> {
  const token = await page.evaluate(() => localStorage.getItem('auth_token'))
  if (!token) return null
  const response = await page.request.get('/api/users/me', { headers: { Authorization: `Bearer ${token}` } })
  if (response.status() === 401) return null
  expect(response.ok(), `/api/users/me answered ${response.status()}`).toBe(true)
  return await response.json()
}

/** Waits until the header shows a signed-in user, or no session at all. */
async function expectSignedIn (page: Page, signedIn: boolean): Promise<void> {
  const avatar = userMenu(page).locator('img')
  if (signedIn) {
    await expect(avatar, 'the header does not show a signed-in user').toBeVisible()
  } else {
    await expect(avatar, 'the header still shows a signed-in user').toHaveCount(0)
    await expect.poll(() => page.evaluate(() => localStorage.getItem('auth_token')), { message: 'a session token is still stored' }).toBeNull()
  }
}

/**
 * Makes `userKey` the signed-in user from any start: a fresh page, signed out, already
 * that user (nothing to do), or another user (signs that one out first). Verifies the
 * resulting identity with the backend. Stays on the current page unless the page is blank.
 */
export async function ensureLoggedIn (page: Page, userKey: string): Promise<void> {
  const user = fixture.user(userKey)
  await openApp(page)
  const current = await storedUser(page)
  if (current?.username === user.username) {
    await expectSignedIn(page, true)
    return
  }
  if (current) await logOut(page)
  await expectSignedIn(page, false) // a rejected stored token is forgotten on restore
  await userMenu(page).click()
  await page.locator('.q-menu').getByText('Log In', { exact: true }).click()
  await page.getByLabel('Email or Username').fill(user.username)
  await page.getByLabel('Password', { exact: true }).fill(user.password)
  await page.getByRole('button', { name: 'Log In' }).click()
  // The dialog closes once signed in; a welcome notice may still be left from an earlier login.
  await expect(page.getByLabel('Email or Username'), 'the login dialog did not close').toHaveCount(0)
  await expect(page.getByText(`Welcome, ${user.name}!`).first()).toBeVisible()
  expect((await storedUser(page))?.username, 'signed in as another user').toBe(user.username)
}

/** Signs out through the user menu when signed in; on a fresh or signed-out page, only verifies. */
export async function logOut (page: Page): Promise<void> {
  await openApp(page)
  if (await storedUser(page)) {
    await expectSignedIn(page, true)
    await userMenu(page).click()
    await page.locator('.q-menu').getByText('Log Out', { exact: true }).click()
    await expect(page.getByText('You have been logged out.')).toBeVisible()
    // The menu closes too; signing out is immediate, so it is not left open showing Log In.
    await expect(page.locator('.q-menu')).toHaveCount(0)
  }
  await expectSignedIn(page, false)
}

/**
 * Opens the Search page (keeping the session), runs `query` and waits for the first result.
 */
export async function search (page: Page, query: string): Promise<void> {
  await page.goto('/#/search')
  await closePhoneNavigation(page)
  // The query field is the only textbox in the search form (it has no label).
  await page.getByRole('textbox').first().fill(query)
  await page.keyboard.press('Enter')
  await expect(page.locator('#result-1'), `no results for "${query}"`).toBeVisible()
}

/** Goes to page `n` of the search results with its page number below them. */
export async function goToResultsPage (page: Page, n: number): Promise<void> {
  // The number buttons only: Quasar names the previous/next arrows after their target page too.
  const button = page.locator('.q-pagination__middle').getByRole('button', { name: String(n), exact: true })
  await expect(button, `no results page ${n}`).toHaveCount(1)
  await button.click()
  await expect(page.locator(`#result-${(n - 1) * 10 + 1}`)).toBeVisible()
}

export type SearchResponse = { results: { id: string, text: string }[] }

/**
 * Changes the `/api/search` answers of this page only, for deterministic edge cases the
 * fixture corpus lacks (long passages, many pages). Call before searching; the real
 * response is fetched and passed to `edit`.
 *
 *   await editSearchResults(page, (body) => appendResultCopies(body, 2))
 */
export async function editSearchResults (page: Page, edit: (body: SearchResponse) => void): Promise<void> {
  await page.route('**/api/search', async (route) => {
    const response = await route.fetch()
    const body = await response.json() as SearchResponse
    edit(body)
    await route.fulfill({ response, json: body })
  })
}

/** Appends `copies` copies of the results (for pagination). Copies get ids of no stored chunk. */
export function appendResultCopies (body: SearchResponse, copies: number): void {
  const original = body.results
  for (let copy = 1; copy <= copies; copy++) {
    body.results = body.results.concat(original.map(r => ({ ...r, id: `${r.id.slice(0, -4)}${copy}fff` })))
  }
}

/** A chat assistant answer as `/api/rag` sends it (snake_case). */
export type ChatAnswer = { rag_answer: string, sources: Record<string, unknown>[] }

/**
 * A chat assistant source for a fixture chunk, as the RAG endpoint returns it. The fake
 * profile has no RAG pipeline, so specs answer `/api/rag` themselves (`answerChat`).
 */
export function chatSource (chunkKey: string): Record<string, unknown> {
  const document = fixtureDocumentOf(chunkKey)
  const chunk = fixture.chunk(chunkKey)
  return {
    id: chunk.id,
    text: chunk.text,
    start_page_id: chunk.start_page_id,
    from_page: chunk.from_page,
    to_page: chunk.to_page,
    document: document.id,
    order: chunk.order,
    document_object: { id: document.id, ...document.properties }
  }
}

function fixtureDocumentOf (chunkKey: string) {
  const document = corpus.documents.find((d) => d.chunks.some((c) => c.key === chunkKey))
  if (!document) throw new Error(`fixture ${chunkKey} not found`)
  return document
}

/**
 * Answers the questions of this page's chat assistant with `answers`, in order (call
 * before asking). Fails the request when there is no answer left.
 */
export async function answerChat (page: Page, answers: ChatAnswer[]): Promise<void> {
  const queue = [...answers]
  await page.route('**/api/rag', async (route) => {
    const answer = queue.shift()
    if (!answer) return route.fulfill({ status: 500, json: { detail: 'No answer prepared' } })
    await route.fulfill({ json: { ...answer, response_id: crypto.randomUUID(), time_spent: 1 } })
  })
}

/**
 * Answers this page's `/api/quota` with a guest who has used `used` of a $0.25 allowance
 * (near the limit from $0.20, used up at $0.25), for allowance states the profile's cheap
 * fake calls do not reach. Returns the reset time (the next UTC midnight).
 */
export async function answerGuestQuota (page: Page, used: number): Promise<Date> {
  const reset = new Date(Date.UTC(new Date().getUTCFullYear(), new Date().getUTCMonth(), new Date().getUTCDate() + 1))
  await page.route('**/api/quota', (route) => route.fulfill({
    json: {
      principal: 'guest',
      day: new Date().toISOString().slice(0, 10),
      limit_usd: 0.25,
      used_usd: used,
      charged_usd: used,
      reserved_usd: 0,
      remaining_usd: Math.max(0, 0.25 - used),
      reset_at: reset.toISOString(),
      near_limit: used >= 0.2,
      exhausted: used >= 0.25
    }
  }))
  return reset
}

/** Asks the chat assistant `question` and waits until its answer is shown. */
export async function askChat (page: Page, question: string): Promise<void> {
  const input = page.getByPlaceholder('Vaše otázka?')
  const answers = page.locator('.message-bubble')
  const before = await answers.count()
  await input.fill(question)
  await input.press('Enter')
  await expect(answers, `no answer to "${question}"`).toHaveCount(before + 2)
  await expect(input).toBeEnabled()
}

/** The rail icon of a right sidebar panel; clicking it shows the panel. */
export function sidebarPanelButton (page: Page, label: string): Locator {
  return page.locator('.q-drawer--right').getByRole('listitem', { name: label, exact: true })
}

/** Opens a collection's document view through the UI, as a user would. */
export async function openDocument (page: Page, collectionKey: string, documentKey: string): Promise<void> {
  await page.locator('.q-drawer').getByText('Collections', { exact: true }).click()
  await page.getByText(fixture.collection(collectionKey).name, { exact: true }).click()
  await page.getByText('Documents & Tagging').click()
  await page.getByText(fixture.document(documentKey).properties.title, { exact: true }).click()
  await expect(page.getByText('Document detail')).toBeVisible()
}

export function chunkText (page: Page, chunkKey: string): Locator {
  return page.locator(`.chunk-annotator[data-chunk-id="${fixture.chunk(chunkKey).id}"]`)
}

/** The rendered annotation for a fixture span: a tagged segment with the span's offsets. */
export function annotation (page: Page, spanKey: string): Locator {
  const span = fixture.span(spanKey)
  const chunkId = byKey(corpus.documents.flatMap((d) => d.chunks), span.chunk).id
  return page.locator(
    `.chunk-annotator[data-chunk-id="${chunkId}"] .text-segment.is-tagged` +
    `[data-start="${span.start}"][data-end="${span.end}"]`
  )
}

/** A bearer token for API calls a test makes itself (setup and cleanup). */
export async function apiToken (request: APIRequestContext, userKey: string): Promise<string> {
  const user = fixture.user(userKey)
  const response = await request.post('/api/auth/jwt/login', { form: { username: user.username, password: user.password } })
  expect(response.ok()).toBe(true)
  return (await response.json()).access_token
}

/** Deletes the unresolved AI suggestions a test created (fixture spans of other tags stay). */
export async function deleteSuggestions (
  request: APIRequestContext, userKey: string, collectionKey: string, documentKey: string, tagKey: string
): Promise<void> {
  const tag = fixture.tag(tagKey)
  const response = await request.post('/api/ai/auto_spans/delete', {
    headers: { Authorization: `Bearer ${await apiToken(request, userKey)}` },
    data: {
      collection_id: fixture.collection(collectionKey).id,
      document_id: fixture.document(documentKey).id,
      tag_ids: [tag.id]
    }
  })
  expect(response.ok()).toBe(true)
}

/**
 * Selects text in the document view as a mouse drag would and releases the mouse.
 * Offsets are within each chunk's own text; the end may lie in a later chunk.
 */
export async function selectText (
  page: Page, startChunkKey: string, start: number, endChunkKey: string, end: number
): Promise<void> {
  const points = [
    { chunkId: fixture.chunk(startChunkKey).id, offset: start },
    { chunkId: fixture.chunk(endChunkKey).id, offset: end }
  ]
  // The text may not be rendered yet right after the document opens.
  for (const { chunkId } of points) {
    await expect(page.locator(`.chunk-annotator[data-chunk-id="${chunkId}"] .text-segment`).first()).toBeVisible()
  }
  await page.evaluate((points) => {
    const locate = ({ chunkId, offset }: { chunkId: string, offset: number }) => {
      const segments = document.querySelectorAll<HTMLElement>(`.chunk-annotator[data-chunk-id="${chunkId}"] .text-segment`)
      for (const segment of Array.from(segments)) {
        const segmentStart = Number(segment.dataset.start)
        if (offset >= segmentStart && offset <= Number(segment.dataset.end)) {
          const text = Array.from(segment.childNodes).find((n) => n.nodeType === Node.TEXT_NODE)!
          return { node: text, offset: offset - segmentStart }
        }
      }
      throw new Error(`offset ${offset} not rendered in chunk ${chunkId}`)
    }
    const from = locate(points[0])
    const to = locate(points[1])
    const range = document.createRange()
    range.setStart(from.node, from.offset)
    range.setEnd(to.node, to.offset)
    const selection = window.getSelection()!
    selection.removeAllRanges()
    selection.addRange(range)
    const rect = range.getBoundingClientRect()
    document.querySelector('.document-text')!.dispatchEvent(
      new MouseEvent('mouseup', { bubbles: true, clientX: rect.right, clientY: rect.bottom })
    )
  }, points)
}

/** Deletes the annotations of a collection that are not part of the fixture corpus. */
export async function deleteAddedSpans (request: APIRequestContext, userKey: string, collectionKey: string): Promise<void> {
  const headers = { Authorization: `Bearer ${await apiToken(request, userKey)}` }
  const fixtureIds = new Set(corpus.spans.map((s) => s.id))
  const response = await request.get('/api/tag_spans', { headers, params: { collection_id: fixture.collection(collectionKey).id } })
  expect(response.ok()).toBe(true)
  for (const span of await response.json() as { id: string }[]) {
    if (fixtureIds.has(span.id)) continue
    // A span is addressed within its collection (annotation tenants, #327).
    const params = { collection_id: fixture.collection(collectionKey).id }
    expect((await request.delete(`/api/tag_spans/${span.id}`, { headers, params })).ok()).toBe(true)
  }
}

/** Removes a chunk from a collection; does nothing when it is not a member. */
export async function removeChunk (
  request: APIRequestContext, userKey: string, collectionKey: string, chunkKey: string
): Promise<void> {
  await request.delete(
    `/api/user_collections/${fixture.collection(collectionKey).id}/chunks/${fixture.chunk(chunkKey).id}`,
    { headers: { Authorization: `Bearer ${await apiToken(request, userKey)}` } }
  )
}
