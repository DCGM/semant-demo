import { expect, test, type Locator, type Page, type Request } from '@playwright/test'
import {
  annotation, apiToken, chunkText, deleteAddedSpans, deleteAddedTags, deleteSuggestions, ensureLoggedIn, fixture, openDocument, removeChunk,
  selectText, sidebarPanelButton
} from './support'

// Document viewer interactions: text selection and annotation editing, the span gutter,
// the tags and AI Tagging panels, and chunk membership. Each test removes what it added.

test.afterEach(async ({ request }) => {
  await deleteAddedSpans(request, 'owner', 'chronicles')
  await deleteAddedTags(request, 'owner', 'chronicles')
  await deleteSuggestions(request, 'owner', 'chronicles', 'chronicle', 'person')
  await removeChunk(request, 'owner', 'newspapers', 'chronicle_2')
})

const popover = (page: Page) => page.locator('.annotation-popover')

/** A tagged segment of a chunk with the given offsets. */
const taggedSegment = (page: Page, chunkKey: string, start: number, end: number) =>
  chunkText(page, chunkKey).locator(`.text-segment.is-tagged[data-start="${start}"][data-end="${end}"]`)

const showChunkGutter = (page: Page) => page.locator('button[title="Show/hide chunk gutter"]').click()

/** The tallest span marker: a span across two chunks covers more lines than a word. */
async function tallestMarker (page: Page): Promise<Locator> {
  const markers = page.locator('.gutter-item')
  let tallest = 0
  let height = 0
  for (let i = 0; i < await markers.count(); i++) {
    const box = await markers.nth(i).boundingBox()
    if (box && box.height > height) { tallest = i; height = box.height }
  }
  return markers.nth(tallest)
}

test('a selection across two chunks is tagged, marked in the gutter and deleted again', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  // Approved fixture spans only: the AI suggestion is hidden outside the AI Tagging panel.
  await expect(page.locator('.gutter-item')).toHaveCount(2)

  const chunk1Length = fixture.chunk('chronicle_1').text.length
  await selectText(page, 'chronicle_1', 62, 'chronicle_2', 8)
  await expect(popover(page).getByText('Select tag')).toBeVisible()
  await popover(page).locator('.tag-row').filter({ hasText: fixture.tag('place').name }).click()

  await expect(taggedSegment(page, 'chronicle_1', 62, chunk1Length)).toBeVisible()
  await expect(taggedSegment(page, 'chronicle_2', 0, 8)).toBeVisible()
  await expect(page.locator('.gutter-item')).toHaveCount(3)

  await (await tallestMarker(page)).click()
  await expect(popover(page).getByRole('button', { name: 'Change tag' })).toBeVisible()
  await popover(page).getByRole('button', { name: 'Delete' }).click()

  await expect(page.locator('.gutter-item')).toHaveCount(2)
  await expect(chunkText(page, 'chronicle_2').locator('.text-segment[data-start="0"]')).not.toHaveClass(/is-tagged/)
  await expect(annotation(page, 'novak_manual')).toBeVisible()
})

test('a click on tagged text opens its span like its gutter label', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await expect(page.locator('.gutter-item')).toHaveCount(2)

  await annotation(page, 'novak_manual').click()
  await expect(popover(page).getByRole('button', { name: 'Change tag' })).toBeVisible()
  await expect(page.locator('.tag-card.is-active')).toContainText(fixture.tag('person').name)
})

test('a span someone else changed meanwhile is not deleted, and shows as it is now', async ({ page, request }) => {
  const novak = fixture.span('novak_manual')
  const retag = async (tag: string, userKey: string) => {
    const response = await request.patch(`/api/tag_spans/${novak.id}`, {
      headers: { Authorization: `Bearer ${await apiToken(request, userKey)}` },
      params: { collection_id: fixture.collection('chronicles').id },
      data: { tagId: fixture.tag(tag).id }
    })
    expect(response.ok()).toBe(true)
  }
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  try {
    await annotation(page, 'novak_manual').click()
    await expect(popover(page).getByRole('button', { name: 'Delete' })).toBeVisible()
    await retag('place', 'annotator') // a collaborator's edit after this page loaded the span

    await popover(page).getByRole('button', { name: 'Delete' }).click()
    await expect(page.getByText('Someone else changed this annotation meanwhile; nothing was saved.')).toBeVisible()
    await expect(annotation(page, 'novak_manual')).toBeVisible()
    await annotation(page, 'novak_manual').click()
    await expect(page.locator('.tag-card.is-active')).toContainText(fixture.tag('place').name)
  } finally {
    await retag('person', 'owner')
  }
})

test('dragging a span\'s start into the previous chunk moves the same span there', async ({ page, request }) => {
  const brno = fixture.span('brno_manual') // "Brně" on chronicle_2
  const collectionId = fixture.collection('chronicles').id
  const headers = { Authorization: `Bearer ${await apiToken(request, 'owner')}` }
  const chunk1Length = fixture.chunk('chronicle_1').text.length
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  try {
    await annotation(page, 'brno_manual').click()
    await expect(popover(page).getByRole('button', { name: 'Change tag' })).toBeVisible()

    // Drag the start handle onto "hostinci" in chronicle_1 (#436).
    const handle = await page.locator('.selection-handle.handle-start').boundingBox()
    const target = await page.evaluate(({ chunkId, offset }) => {
      const segments = document.querySelectorAll<HTMLElement>(`.chunk-annotator[data-chunk-id="${chunkId}"] .text-segment`)
      for (const segment of Array.from(segments)) {
        const start = Number(segment.dataset.start)
        if (offset >= start && offset < Number(segment.dataset.end)) {
          const range = document.createRange()
          const text = Array.from(segment.childNodes).find((n) => n.nodeType === Node.TEXT_NODE)!
          range.setStart(text, offset - start)
          range.setEnd(text, offset - start + 1)
          const rect = range.getBoundingClientRect()
          return { x: rect.left + 1, y: rect.top + rect.height / 2 }
        }
      }
      throw new Error('offset not rendered')
    }, { chunkId: fixture.chunk('chronicle_1').id, offset: 60 })
    await page.mouse.move(handle!.x + handle!.width / 2, handle!.y + handle!.height / 2)
    await page.mouse.down()
    await page.mouse.move(target.x, target.y, { steps: 10 })
    await page.mouse.up()
    await popover(page).getByRole('button', { name: 'Save position' }).click()

    await expect(taggedSegment(page, 'chronicle_1', 60, chunk1Length)).toBeVisible()
    await expect(taggedSegment(page, 'chronicle_2', 0, brno.end)).toBeVisible()
    await expect(page.locator('.gutter-item')).toHaveCount(2)
    // Stored on chronicle_1 under the same id, not as a new span.
    const response = await request.get('/api/tag_spans', {
      headers, params: { collection_id: collectionId, chunk_id: fixture.chunk('chronicle_1').id }
    })
    const moved = (await response.json() as { id: string, start: number, end: number }[]).find((s) => s.id === brno.id)
    expect(moved).toMatchObject({ start: 60, end: chunk1Length + brno.end })
  } finally {
    const restored = await request.patch(`/api/tag_spans/${brno.id}`, {
      headers,
      params: { collection_id: collectionId },
      data: { chunkId: fixture.chunk('chronicle_2').id, start: brno.start, end: brno.end }
    })
    expect(restored.ok()).toBe(true)
  }
})

test('a selection after clicking a marker opens the tag picker instead of reusing its tag', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')

  // The Jan Novák marker in the first chunk.
  await page.locator('.gutter-item').first().click()
  await expect(popover(page).getByRole('button', { name: 'Change tag' })).toBeVisible()
  await expect(page.locator('.tag-card.is-active')).toContainText(fixture.tag('person').name)

  const text = fixture.chunk('chronicle_2').text
  const start = text.indexOf('Jan Novák')
  await selectText(page, 'chronicle_2', start, 'chronicle_2', start + 'Jan Novák'.length)

  await expect(popover(page).getByText('Select tag')).toBeVisible()
  await expect(taggedSegment(page, 'chronicle_2', start, start + 'Jan Novák'.length)).toHaveCount(0)
  await expect(page.locator('.gutter-item')).toHaveCount(2)

  await page.keyboard.press('Escape')
  await expect(popover(page)).toHaveCount(0)
  await expect(page.locator('.tag-card.is-active')).toHaveCount(0)
})

// #479: a tag focused from the tags panel tags each new selection directly.
test('a tag focused in the tags panel tags new selections directly until Escape', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await expect(page.locator('.gutter-item')).toHaveCount(2)
  const place = fixture.tag('place').name

  await page.getByRole('button', { name: `Tag with ${place}` }).click()
  await expect(page.locator('.tag-card.is-focused')).toContainText(place)
  await expect(page.getByRole('status').filter({ hasText: 'Tagging with:' })).toContainText(place)
  // The other tag's marker (Jan Novák) fades; Brno's stays.
  await expect(page.locator('.gutter-item.is-faded')).toHaveCount(1)

  const text = fixture.chunk('chronicle_1').text
  const start = text.indexOf('hejtman')
  await selectText(page, 'chronicle_1', start, 'chronicle_1', start + 'hejtman'.length)
  await expect(taggedSegment(page, 'chronicle_1', start, start + 'hejtman'.length)).toBeVisible()
  await expect(page.locator('.gutter-item')).toHaveCount(3)
  await expect(popover(page)).toHaveCount(0)

  // A click on an annotation still opens it; Escape closes it first, then ends the focus.
  await annotation(page, 'brno_manual').click()
  await expect(popover(page).getByRole('button', { name: 'Change tag' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(popover(page)).toHaveCount(0)
  await expect(page.locator('.tag-card.is-focused')).toContainText(place)
  await page.keyboard.press('Escape')
  await expect(page.getByText('Tagging with:')).toHaveCount(0)
  await expect(page.locator('.tag-card.is-focused')).toHaveCount(0)
  await expect(page.locator('.gutter-item.is-faded')).toHaveCount(0)
  const hostinci = text.indexOf('hostinci')
  await selectText(page, 'chronicle_1', hostinci, 'chronicle_1', hostinci + 'hostinci'.length)
  await expect(popover(page).getByText('Select tag')).toBeVisible()
})

test('a double-clicked word is tagged once with the focused tag', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await expect(page.locator('.gutter-item')).toHaveCount(2)
  await page.getByRole('button', { name: `Tag with ${fixture.tag('place').name}` }).click()

  const text = fixture.chunk('chronicle_1').text
  const start = text.indexOf('hostinci')
  const word = await chunkText(page, 'chronicle_1').evaluate((chunk, start) => {
    for (const segment of Array.from(chunk.querySelectorAll<HTMLElement>('.text-segment'))) {
      const segmentStart = Number(segment.dataset.start)
      if (start < segmentStart || start >= Number(segment.dataset.end)) continue
      const node = Array.from(segment.childNodes).find((n) => n.nodeType === Node.TEXT_NODE)!
      const range = document.createRange()
      range.setStart(node, start - segmentStart + 1)
      range.setEnd(node, start - segmentStart + 2)
      const box = range.getBoundingClientRect()
      return { x: box.x + box.width / 2, y: box.y + box.height / 2 }
    }
    throw new Error('word not rendered')
  }, start)
  await page.mouse.dblclick(word.x, word.y)

  await expect(taggedSegment(page, 'chronicle_1', start, start + 'hostinci'.length)).toBeVisible()
  await expect(page.locator('.gutter-item')).toHaveCount(3)
  await expect(popover(page)).toHaveCount(0)
})

test('the focus ends with its ✕, a second click on its card, or hiding its tag', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  const person = fixture.tag('person').name
  const personCard = page.locator('.tag-card').filter({ hasText: person })
  const focused = page.locator('.tag-card.is-focused')

  // A click anywhere on the card but its buttons focuses the tag.
  await personCard.locator('.tag-definition').click()
  await expect(focused).toContainText(person)
  await page.getByRole('button', { name: 'Stop tagging with this tag' }).click()
  await expect(focused).toHaveCount(0)

  await personCard.locator('.tag-definition').click()
  await personCard.locator('.tag-nav-row').getByRole('button').last().click() // its buttons don't change it
  await expect(focused).toContainText(person)
  await personCard.locator('.tag-definition').click()
  await expect(focused).toHaveCount(0)

  await personCard.locator('.tag-definition').click()
  await personCard.locator('.visibility-btn').click()
  await expect(focused).toHaveCount(0)
  await expect(annotation(page, 'novak_manual')).toHaveCount(0)
  // Focusing a hidden tag shows it again.
  await personCard.locator('.tag-definition').click()
  await expect(focused).toContainText(person)
  await expect(annotation(page, 'novak_manual')).toBeVisible()
})

test('the tags panel sorts its tags by name or by number of annotations', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await expect(page.locator('.gutter-item')).toHaveCount(2)
  const tagNames = page.locator('.tag-card .tag-name')
  const [place, person] = [fixture.tag('place').name, fixture.tag('person').name]
  // One annotation each: the tie is broken by name.
  await expect(tagNames).toHaveText([place, person])

  // A second annotation of Osoba.
  const text = fixture.chunk('chronicle_2').text
  const start = text.indexOf('Jan Novák')
  await selectText(page, 'chronicle_2', start, 'chronicle_2', start + 'Jan Novák'.length)
  await popover(page).locator('.tag-row').filter({ hasText: person }).click()
  await expect(page.locator('.gutter-item')).toHaveCount(3)
  // Counts are not re-sorted while annotating; choosing the sort again does it.
  await expect(tagNames).toHaveText([place, person])
  const byCount = page.getByRole('button', { name: 'Sort tags by number of annotations' })
  await expect(byCount).toHaveAttribute('aria-pressed', 'true')
  await byCount.click()
  await expect(tagNames).toHaveText([person, place])

  const byName = page.getByRole('button', { name: 'Sort tags by name' })
  await byName.click()
  await expect(byName).toHaveAttribute('aria-pressed', 'true')
  await expect(byCount).toHaveAttribute('aria-pressed', 'false')
  await expect(tagNames).toHaveText([place, person])

  // The choice is remembered.
  await page.reload()
  await expect(page.locator('.gutter-item')).toHaveCount(3)
  await expect(page.getByRole('button', { name: 'Sort tags by name' })).toHaveAttribute('aria-pressed', 'true')
  await expect(tagNames).toHaveText([place, person])
  await page.getByRole('button', { name: 'Sort tags by number of annotations' }).click()
  await expect(tagNames).toHaveText([person, place])
})

// #379: the create-tag dialog covers the popover (see the tests further down), and Escape
// there belongs to the dialog, so the new tag still goes onto the selection.
test('Escape in the create-tag dialog keeps the selection the new tag goes onto', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await expect(page.locator('.gutter-item')).toHaveCount(2)

  const start = fixture.chunk('chronicle_1').text.indexOf('hostinci')
  const end = start + 'hostinci'.length
  await selectText(page, 'chronicle_1', start, 'chronicle_1', end)
  await popover(page).getByText('Create new tag').click()
  const dialog = page.locator('.q-dialog')
  await expect(dialog.getByLabel('Tag Name')).toBeVisible()

  // Escape closes the empty dialog (#479) but leaves the selection and its popover.
  await page.keyboard.press('Escape')
  await expect(dialog.getByLabel('Tag Name')).toHaveCount(0)
  await expect(popover(page)).toBeVisible()
  await popover(page).getByText('Create new tag').click()
  await dialog.getByLabel('Tag Name').fill('Inn')
  await dialog.getByLabel('Tag Shorthand').fill('INN')
  await dialog.getByRole('button', { name: 'Create' }).click()

  await expect(taggedSegment(page, 'chronicle_1', start, end)).toBeVisible()
  await expect(popover(page)).toHaveCount(0)
})

test('closing the popover without an open dialog discards the selection', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await expect(page.locator('.gutter-item')).toHaveCount(2)

  const start = fixture.chunk('chronicle_1').text.indexOf('hostinci')
  await selectText(page, 'chronicle_1', start, 'chronicle_1', start + 'hostinci'.length)
  await expect(popover(page).getByText('Create new tag')).toBeVisible()

  await popover(page).locator('.popover-close').click()
  await expect(popover(page)).toHaveCount(0)
})

/**
 * A request with the given method that writes one span: `POST /api/tag_spans` creates it,
 * `PATCH` and `DELETE /api/tag_spans/{id}` change or delete it. Not a span load
 * (`POST /api/tag_spans/batch`), which the reader may send at any time.
 */
function isSpanWrite (request: Request, method: string): boolean {
  const path = method === 'POST' ? /\/api\/tag_spans$/ : /\/api\/tag_spans\/[^/]+$/
  return request.method() === method && path.test(new URL(request.url()).pathname)
}

/**
 * Holds span writes with the given method (POST creates, DELETE deletes) until `release`
 * is called, and counts them. Lets a test act while a request it started is still in flight.
 */
async function holdSpanRequests (page: Page, method = 'POST'): Promise<{ count: () => number, release: () => void }> {
  let requests = 0
  let release!: () => void
  const released = new Promise<void>((resolve) => { release = resolve })
  await page.route('**/api/tag_spans**', async (route) => {
    if (!isSpanWrite(route.request(), method)) return route.fallback()
    requests++
    await released
    await route.continue()
  })
  return { count: () => requests, release }
}

test('a tag request that finishes late keeps the newer selection open', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  const held = await holdSpanRequests(page)

  await selectText(page, 'chronicle_2', 0, 'chronicle_2', 8)
  await popover(page).locator('.tag-row').filter({ hasText: fixture.tag('place').name }).click()
  await expect.poll(held.count).toBe(1)

  // A new selection while the first span is still being saved.
  const text = fixture.chunk('chronicle_2').text
  const start = text.indexOf('Jan Novák')
  await selectText(page, 'chronicle_2', start, 'chronicle_2', start + 'Jan Novák'.length)
  await expect(popover(page).getByText('Select tag')).toBeVisible()

  held.release()
  await expect(taggedSegment(page, 'chronicle_2', 0, 8)).toBeVisible()
  await expect(popover(page).getByText('Select tag')).toBeVisible()

  await popover(page).locator('.tag-row').filter({ hasText: fixture.tag('person').name }).click()
  await expect(taggedSegment(page, 'chronicle_2', start, start + 'Jan Novák'.length)).toBeVisible()
  await expect(page.locator('.gutter-item')).toHaveCount(4)
})

test('a double-click on a tag row creates one span', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await expect(page.locator('.gutter-item')).toHaveCount(2)
  const held = await holdSpanRequests(page)

  await selectText(page, 'chronicle_2', 0, 'chronicle_2', 8)
  await popover(page).locator('.tag-row').filter({ hasText: fixture.tag('place').name }).dblclick()
  await expect.poll(held.count).toBe(1)
  // While the span is saved, the picker shows it is busy instead of taking another pick.
  await expect(popover(page)).toHaveClass(/is-busy/)

  held.release()
  await expect(taggedSegment(page, 'chronicle_2', 0, 8)).toBeVisible()
  await expect(popover(page)).toHaveCount(0)
  await expect(page.locator('.gutter-item')).toHaveCount(3)
  expect(held.count()).toBe(1)
})

test('a new selection clears the AI suggestion highlighted from its marker', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Tagging').click()
  const card = page.locator('.auto-span-card').filter({ hasText: fixture.tag('place').name })

  await page.locator('.gutter-item.is-auto').click()
  await expect(card).toHaveClass(/is-highlighted/)

  await selectText(page, 'chronicle_2', 0, 'chronicle_2', 8)
  await expect(popover(page).getByText('Select tag')).toBeVisible()
  await expect(card).not.toHaveClass(/is-highlighted/)
})

test('a new selection keeps the AI suggestion reached with the panel arrows', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await sidebarPanelButton(page, 'AI Tagging').click()
  const card = page.locator('.auto-span-card').filter({ hasText: fixture.tag('place').name })
  const nav = page.locator('.ai-tag-nav')

  await nav.locator('.q-btn').last().click()
  await expect(nav.locator('.ai-tag-nav-counter')).toHaveText('1/1')
  await expect(card).toHaveClass(/is-highlighted/)

  await selectText(page, 'chronicle_2', 0, 'chronicle_2', 8)
  await expect(popover(page).getByText('Select tag')).toBeVisible()
  await expect(card).toHaveClass(/is-highlighted/)
  await expect(nav.locator('.ai-tag-nav-counter')).toHaveText('1/1')
})

test('a delete that finishes late keeps the newer selection open', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await selectText(page, 'chronicle_2', 0, 'chronicle_2', 8)
  const person = fixture.tag('person')
  await popover(page).locator('.tag-row').filter({ hasText: person.name }).click()
  // Its marker is the lower of the two person markers: the fixture one is in the first chunk.
  const personMarkers = page.locator('.gutter-item').filter({ hasText: person.shorthand })
  await expect(personMarkers).toHaveCount(2)
  const [first, second] = [personMarkers.first(), personMarkers.last()]
  const marker = (await first.boundingBox())!.y > (await second.boundingBox())!.y ? first : second
  const held = await holdSpanRequests(page, 'DELETE')

  await marker.click()
  await popover(page).getByRole('button', { name: 'Delete' }).click()
  await expect.poll(held.count).toBe(1)

  const text = fixture.chunk('chronicle_2').text
  const start = text.indexOf('Jan Novák')
  await selectText(page, 'chronicle_2', start, 'chronicle_2', start + 'Jan Novák'.length)
  await expect(popover(page).getByText('Select tag')).toBeVisible()

  held.release()
  await expect(personMarkers).toHaveCount(1)
  await expect(popover(page).getByText('Select tag')).toBeVisible()
})

/** Makes span writes with the given method fail with a 500; span loads still work. */
async function failSpanRequests (page: Page, method: string) {
  await page.route('**/api/tag_spans**', (route) => isSpanWrite(route.request(), method)
    ? route.fulfill({ status: 500, body: 'Internal Server Error' })
    : route.fallback())
}

/** Errors the page did not handle, such as an uncaught promise rejection. */
function collectPageErrors (page: Page): Error[] {
  const errors: Error[] = []
  page.on('pageerror', (err) => errors.push(err))
  return errors
}

test('a tag that fails to save is reported and keeps the selection open', async ({ page }) => {
  const pageErrors = collectPageErrors(page)
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await expect(page.locator('.gutter-item')).toHaveCount(2)
  await failSpanRequests(page, 'POST')

  await selectText(page, 'chronicle_2', 0, 'chronicle_2', 8)
  await popover(page).locator('.tag-row').filter({ hasText: fixture.tag('place').name }).click()

  await expect(page.locator('.q-notification').filter({ hasText: 'The tag could not be saved.' })).toBeVisible()
  await expect(popover(page).getByText('Select tag')).toBeVisible()
  await expect(popover(page)).not.toHaveClass(/is-busy/)
  await expect(page.locator('.gutter-item')).toHaveCount(2)
  expect(pageErrors).toEqual([])
})

test('a retag that fails is reported and keeps the span\'s tag', async ({ page }) => {
  const pageErrors = collectPageErrors(page)
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await failSpanRequests(page, 'PATCH')
  const person = fixture.tag('person')

  // The Jan Novák marker in the first chunk.
  await page.locator('.gutter-item').first().click()
  await popover(page).getByRole('button', { name: 'Change tag' }).click()
  await popover(page).locator('.tag-row').filter({ hasText: fixture.tag('place').name }).click()

  await expect(page.locator('.q-notification').filter({ hasText: 'The tag could not be changed.' })).toBeVisible()
  await expect(popover(page).locator('.tag-row.is-active')).toContainText(person.name)
  await expect(page.locator('.tag-card.is-active')).toContainText(person.name)
  await expect(page.locator('.gutter-item').first()).toContainText(person.shorthand)
  expect(pageErrors).toEqual([])
})

test('the tags panel hides tags, steps through their annotations and is searched with Ctrl+F', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  const personCard = page.locator('.tag-card').filter({ hasText: fixture.tag('person').name })

  await personCard.locator('.visibility-btn').click()
  await expect(annotation(page, 'novak_manual')).toHaveCount(0)
  await expect(annotation(page, 'brno_manual')).toBeVisible()
  await page.getByRole('button', { name: 'Show all tags' }).click()
  await expect(annotation(page, 'novak_manual')).toBeVisible()

  await expect(personCard.locator('.tag-nav-counter')).toHaveText('–/1')
  await personCard.locator('.tag-nav-row').getByRole('button').last().click()
  await expect(personCard.locator('.tag-nav-counter')).toHaveText('1/1')

  await page.locator('.document-text').click()
  await page.keyboard.press('Control+f')
  await expect(page.getByPlaceholder('Search tags…')).toBeFocused()
  await page.keyboard.type(fixture.tag('place').name)
  await expect(page.locator('.tag-card')).toHaveCount(1)
  await expect(page.locator('.tag-card')).toContainText(fixture.tag('place').name)
})

test('AI suggestions show only with the AI Tagging panel and highlight between card and gutter', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await expect(annotation(page, 'novak_manual')).toBeVisible()
  await expect(annotation(page, 'lhota_automatic')).toHaveCount(0)

  await sidebarPanelButton(page, 'AI Tagging').click()
  await expect(annotation(page, 'lhota_automatic')).toBeVisible()
  const card = page.locator('.auto-span-card').filter({ hasText: fixture.tag('place').name })
  await expect(card).toHaveCount(1)
  await card.click()
  await expect(card).toHaveClass(/is-highlighted/)
  await expect(page.locator('.gutter-item.is-highlighted')).toHaveCount(1)

  await sidebarPanelButton(page, 'Tags').click()
  await expect(annotation(page, 'lhota_automatic')).toHaveCount(0)
  await expect(page.locator('.gutter-item.is-highlighted')).toHaveCount(0)
})

test('Suggest tags on a selection runs in the AI Tagging panel', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')

  await selectText(page, 'chronicle_1', 0, 'chronicle_1', 43)
  await popover(page).getByRole('button', { name: 'Suggest tags' }).click()
  await popover(page).getByRole('button', { name: 'None' }).click()
  await popover(page).locator('.tag-row').filter({ hasText: fixture.tag('person').name }).click()
  await expect(popover(page).getByText('1 / 2 selected')).toBeVisible()
  await popover(page).getByRole('button', { name: 'Run AI' }).click()

  await expect(popover(page)).toHaveCount(0)
  await expect(sidebarPanelButton(page, 'AI Tagging')).toHaveAttribute('aria-current', 'true')
  await expect(page.locator('.auto-span-card').filter({ hasText: fixture.tag('person').name }).first()).toBeVisible()
})

test('the owner adds a preview chunk to the collection and removes it with the bulk bar', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'newspapers', 'chronicle')
  await expect(chunkText(page, 'chronicle_3')).toBeVisible()
  await expect(chunkText(page, 'chronicle_2')).toHaveCount(0)

  await page.getByRole('button', { name: 'Load previous', exact: true }).first().click()
  await expect(chunkText(page, 'chronicle_2')).toHaveClass(/chunk-preview/)
  // The chunk gutter starts hidden on every visit.
  await showChunkGutter(page)
  await chunkText(page, 'chronicle_2').hover()
  await page.locator('button[title="Add to collection"]').click()
  await expect(chunkText(page, 'chronicle_2')).not.toHaveClass(/chunk-preview/)

  await page.reload()
  await expect(chunkText(page, 'chronicle_2')).toBeVisible()
  await expect(chunkText(page, 'chronicle_2')).not.toHaveClass(/chunk-preview/)

  await showChunkGutter(page)
  await page.locator('.chunk-checkbox-item').first().click()
  await expect(page.locator('.bulk-action-bar')).toContainText('1 selected')
  await page.locator('.bulk-action-bar').getByRole('button', { name: 'Remove' }).click()
  await expect(page.locator('.bulk-action-bar')).toHaveCount(0)
  await expect(chunkText(page, 'chronicle_2')).toHaveClass(/chunk-preview/)

  await page.reload()
  await expect(chunkText(page, 'chronicle_3')).toBeVisible()
  await expect(chunkText(page, 'chronicle_2')).toHaveCount(0)
})

test('a gap between the collection\'s chunks is shown and filled with the stored text', async ({ page, request }) => {
  // In "newspapers" the document then has chunks 0 and 2: chunk 1 is missing between them.
  const headers = { Authorization: `Bearer ${await apiToken(request, 'owner')}` }
  const added = await request.post(
    `/api/user_collections/${fixture.collection('newspapers').id}/chunks/${fixture.chunk('chronicle_1').id}`, { headers }
  )
  expect(added.ok()).toBe(true)
  try {
    await ensureLoggedIn(page, 'owner')
    await openDocument(page, 'newspapers', 'chronicle')
    const gap = page.locator('.gap-row')
    await expect(gap).toContainText('1 chunk not shown')
    await expect(chunkText(page, 'chronicle_2')).toHaveCount(0)

    await gap.getByRole('button', { name: 'Load all missing' }).click()
    await expect(gap).toHaveCount(0)
    await expect(chunkText(page, 'chronicle_2')).toHaveClass(/chunk-preview/)
    for (const key of ['chronicle_1', 'chronicle_2', 'chronicle_3']) {
      expect(await chunkText(page, key).textContent()).toBe(fixture.chunk(key).text)
    }
    // The original whitespace is kept, each chunk on its own line.
    await expect(chunkText(page, 'chronicle_2').locator('.text-segment').first()).toHaveCSS('white-space', 'pre-wrap')
    await expect(chunkText(page, 'chronicle_2')).toHaveCSS('display', 'block')
  } finally {
    await removeChunk(request, 'owner', 'newspapers', 'chronicle_1')
  }
})

test('on a narrow window the text, gutters and side panel stay usable', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await page.setViewportSize({ width: 900, height: 800 })
  await page.goto(`/#/collections/${fixture.collection('chronicles').id}/documents/${fixture.document('chronicle').id}`)

  await expect(annotation(page, 'novak_manual')).toBeVisible()
  await expect(page.locator('.gutter-item')).toHaveCount(2)
  // Below 1024 px the sidebar is an overlay that starts closed, so the text keeps the width.
  const sidebar = page.locator('.q-drawer--right')
  await expect(sidebar).toBeHidden()
  await page.getByRole('button', { name: 'Toggle sidebar' }).click()
  await expect(page.locator('.tag-card')).toHaveCount(2)
  await expect(page.locator('.tag-card').first()).toBeVisible()
  // Tap beside the overlay to close it.
  await page.locator('.q-drawer__backdrop:not(.hidden)').first().click({ position: { x: 100, y: 400 } })
  await expect(sidebar).toBeHidden()
})

test('the AI Tagging and tags panels keep their state across panel switches', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  // Retrying assertions: tags load asynchronously after the view opens.
  const tagNames = page.locator('.tag-card .tag-name')
  // The panel re-sorts its tags by span count when the spans arrive (until the user reorders),
  // so wait for them before dragging; otherwise the list can change under the drag (#302).
  await expect(page.locator('.gutter-item')).toHaveCount(2)

  // Manual tag order: drop Osoba on the top half of Místo.
  await expect(tagNames).toHaveText([fixture.tag('place').name, fixture.tag('person').name])
  const person = page.locator('.tag-card').filter({ hasText: fixture.tag('person').name })
  const place = page.locator('.tag-card').filter({ hasText: fixture.tag('place').name })
  await person.dragTo(place, { targetPosition: { x: 40, y: 5 } })
  await expect(tagNames).toHaveText([fixture.tag('person').name, fixture.tag('place').name])

  await sidebarPanelButton(page, 'AI Tagging').click()
  await page.locator('.ai-tag-list').getByText(fixture.tag('person').name, { exact: true }).click()
  await page.getByRole('radio', { name: 'Thorough (every chunk in collection)' }).click()

  await sidebarPanelButton(page, 'Tags').click()
  await expect(tagNames).toHaveText([fixture.tag('person').name, fixture.tag('place').name])

  await sidebarPanelButton(page, 'AI Tagging').click()
  await expect(page.getByRole('radio', { name: 'Thorough (every chunk in collection)' })).toHaveAttribute('aria-checked', 'true')
  await expect(page.locator('.ai-tag-list').getByRole('checkbox', { name: fixture.tag('person').name })).toHaveAttribute('aria-checked', 'true')
  await expect(page.locator('.ai-tag-list').getByRole('checkbox', { name: fixture.tag('place').name })).toHaveAttribute('aria-checked', 'false')
})

/** Whether something else is on top at the centre of the element. */
const covered = (locator: Locator) => locator.evaluate((el) => {
  const box = el.getBoundingClientRect()
  return !el.contains(document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2))
})

// #379: a dialog opened from the popover covers it, so nothing in the popover can be
// clicked (its close button, a second create-tag dialog) until the dialog closes.
test('the create-tag dialog covers the popover until it is closed', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await expect(page.locator('.gutter-item')).toHaveCount(2)

  const start = fixture.chunk('chronicle_1').text.indexOf('hostinci')
  await selectText(page, 'chronicle_1', start, 'chronicle_1', start + 'hostinci'.length)
  const createTag = popover(page).getByText('Create new tag')
  await createTag.click()
  const dialog = page.locator('.q-dialog')
  await expect(dialog.getByLabel('Tag Name')).toBeVisible()

  await expect(popover(page)).toBeVisible()
  await expect.poll(() => covered(createTag)).toBe(true)
  await expect.poll(() => covered(popover(page).locator('.popover-close'))).toBe(true)

  await dialog.getByRole('button', { name: 'Cancel' }).click()
  await expect(dialog).toHaveCount(0)
  await expect.poll(() => covered(createTag)).toBe(false)
})

test('the bulk bar stays below the popover and the dialogs it opens', async ({ page }) => {
  await ensureLoggedIn(page, 'owner')
  await openDocument(page, 'chronicles', 'chronicle')
  await expect(page.locator('.gutter-item')).toHaveCount(2)

  await showChunkGutter(page)
  await page.locator('.chunk-checkbox-item').first().click()
  const bar = page.locator('.bulk-action-bar')
  await expect(bar).toContainText('1 selected')

  const start = fixture.chunk('chronicle_1').text.indexOf('hostinci')
  await selectText(page, 'chronicle_1', start, 'chronicle_1', start + 'hostinci'.length)
  await expect(popover(page)).toBeVisible()
  // Both are fixed children of <body>, so their z-index orders them where they overlap.
  const zIndex = (locator: Locator) => locator.evaluate((el) => Number(getComputedStyle(el).zIndex))
  expect(await zIndex(bar)).toBeLessThan(await zIndex(popover(page)))

  await popover(page).getByText('Create new tag').click()
  await expect(page.locator('.q-dialog').getByLabel('Tag Name')).toBeVisible()
  await expect.poll(() => covered(bar)).toBe(true)
})
