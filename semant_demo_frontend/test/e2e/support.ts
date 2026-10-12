import { expect, type APIRequestContext, type Locator, type Page } from '@playwright/test'
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

export async function logIn (page: Page, userKey: string): Promise<void> {
  const user = fixture.user(userKey)
  await page.goto('/')
  await page.getByRole('button', { name: 'User menu' }).click()
  await page.locator('.q-menu').getByText('Log In', { exact: true }).click()
  await page.getByLabel('Email or Username').fill(user.username)
  await page.getByLabel('Password', { exact: true }).fill(user.password)
  await page.getByRole('button', { name: 'Log In' }).click()
  await expect(page.getByText(`Welcome, ${user.name}!`)).toBeVisible()
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
    expect((await request.delete(`/api/tag_spans/${span.id}`, { headers })).ok()).toBe(true)
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
