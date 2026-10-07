import { expect, type Locator, type Page } from '@playwright/test'
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
  span: (key: string) => byKey(corpus.spans, key)
}

export async function logIn (page: Page, userKey: string): Promise<void> {
  const user = fixture.user(userKey)
  await page.goto('/')
  await page.getByRole('button', { name: 'User menu' }).click()
  await page.getByText('Log In', { exact: true }).click()
  await page.getByLabel('Email or Username').fill(user.username)
  await page.getByLabel('Password', { exact: true }).fill(user.password)
  await page.getByRole('button', { name: 'Log In' }).click()
  await expect(page.getByText(`Welcome, ${user.name}!`)).toBeVisible()
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
