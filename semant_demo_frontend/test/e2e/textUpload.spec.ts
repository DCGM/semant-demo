import { utimesSync, writeFileSync } from 'fs'
import { expect, test, type APIRequestContext } from '@playwright/test'
import { apiToken, ensureLoggedIn, fixture, useViewport } from './support'

// Upload of private text documents into a collection (#785), against the real e2e server
// (fake embeddings). Each test uploads into a collection it creates and deletes: an uploaded
// document is private, so once its collection is gone no other test can see it.

const TEXT = 'Kronika rodu Zahrádků.\n\nRoku 1925 se v obci konala pouť.\n\nKonec zápisu.\n'

async function createCollection (request: APIRequestContext, name: string) {
  const headers = { Authorization: `Bearer ${await apiToken(request, 'owner')}` }
  const response = await request.post('/api/user_collections', { headers, data: { name, color: '#1976d2' } })
  expect(response.status()).toBe(201)
  const { id } = await response.json() as { id: string }
  return { id, remove: async () => { await request.delete(`/api/user_collections/${id}`, { headers }) } }
}

for (const viewport of ['wide', 'phone'] as const) {
  test(`the owner uploads text files with metadata and reads one (${viewport})`, async ({ page, request }) => {
    const collection = await createCollection(request, `Upload test ${viewport}`)
    try {
      await useViewport(page, viewport)
      await ensureLoggedIn(page, 'owner')
      await page.goto(`/#/collections/${collection.id}/documents`)
      await page.getByTestId('upload-text-documents').click()

      const dialog = page.locator('.text-upload-dialog')
      await dialog.getByTestId('upload-files').setInputFiles([
        { name: 'Kronika Zahrádků.txt', mimeType: 'text/plain', buffer: Buffer.from(TEXT) },
        { name: 'Dopis.txt', mimeType: 'text/plain', buffer: Buffer.from('Milá Anno, zdravím z Prahy.') }
      ])
      await dialog.getByTestId('upload-metadata').setInputFiles({
        name: 'metadata.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from('filename,title,author,yearIssued\nKronika Zahrádků.txt,Kronika rodu Zahrádků,Jan Zahrádka,1925\n')
      })
      await expect(dialog.getByTestId('upload-template')).toHaveAttribute('download', /\.csv$/)
      await dialog.getByTestId('upload-submit').click()

      await expect(dialog.getByTestId('upload-results')).toContainText('All 2 documents were added.')
      await expect(dialog.getByTestId('upload-result')).toHaveCount(2)
      await page.screenshot({ path: test.info().outputPath(`upload-results-${viewport}.png`) })

      await dialog.getByRole('link', { name: 'Kronika rodu Zahrádků' }).click()
      await expect(dialog).toBeHidden()
      await expect(page.locator('.doc-header').getByTestId('document-title')).toHaveText('Kronika rodu Zahrádků')
      await expect(page.getByText('Roku 1925 se v obci konala pouť.')).toBeVisible()
      await page.screenshot({ path: test.info().outputPath(`uploaded-document-${viewport}.png`) })

      await page.goto(`/#/collections/${collection.id}/documents`)
      await expect(page.locator('tr', { hasText: 'Dopis' }).getByTestId('document-rights-label')).toHaveText('Restricted')
    } finally {
      await collection.remove()
    }
  })
}

test('an invalid file is reported and nothing is uploaded', async ({ page, request }) => {
  const collection = await createCollection(request, 'Upload test invalid')
  try {
    await useViewport(page, 'wide')
    await ensureLoggedIn(page, 'owner')
    await page.goto(`/#/collections/${collection.id}/documents`)
    await page.getByTestId('upload-text-documents').click()
    const dialog = page.locator('.text-upload-dialog')
    await dialog.getByTestId('upload-files').setInputFiles([
      { name: 'a.txt', mimeType: 'text/plain', buffer: Buffer.from('Text.') },
      { name: 'b.txt', mimeType: 'text/plain', buffer: Buffer.from([0xff, 0xfe, 0x00]) }
    ])
    await dialog.getByTestId('upload-submit').click()

    await expect(dialog.getByTestId('upload-results')).toContainText('No document was added.')
    await expect(dialog.getByTestId('upload-result').filter({ hasText: 'b.txt' })).toContainText('not UTF-8')
    await expect(dialog.getByTestId('upload-result').filter({ hasText: 'a.txt' })).toContainText('Not uploaded')
    await expect(dialog.getByTestId('upload-next')).toContainText('correct or remove them')
    await page.screenshot({ path: test.info().outputPath('upload-invalid.png') })
    await dialog.getByRole('button', { name: 'Close', exact: true }).click()
    await expect(page.getByText('Documents (0 items)')).toBeVisible()
  } finally {
    await collection.remove()
  }
})

test('a language that is no ISO 639 code is refused; a CSV corrected after it was chosen is asked for again', async ({ page, request }) => {
  const collection = await createCollection(request, 'Upload test language')
  try {
    await useViewport(page, 'wide')
    await ensureLoggedIn(page, 'owner')
    await page.goto(`/#/collections/${collection.id}/documents`)
    await page.getByTestId('upload-text-documents').click()
    const dialog = page.locator('.text-upload-dialog')
    // A real file on disk, so the browser knows when it changes after it was chosen.
    const csv = test.info().outputPath('metadata.csv')
    writeFileSync(csv, 'filename,language\na.txt,polish\n')
    await dialog.getByTestId('upload-files').setInputFiles({ name: 'a.txt', mimeType: 'text/plain', buffer: Buffer.from(TEXT) })
    await dialog.getByTestId('upload-metadata').setInputFiles(csv)
    await dialog.getByTestId('upload-submit').click()
    await expect(dialog.getByTestId('upload-result')).toContainText(
      "language 'polish' is not a language code: use a two- or three-letter ISO 639 code (e.g. cs or ces for Czech")

    // The user corrects the CSV in an editor and uploads again without choosing it again.
    writeFileSync(csv, 'filename,language\na.txt,ces\n')
    utimesSync(csv, new Date(), new Date(Date.now() + 5000))
    await dialog.getByTestId('upload-submit').click()
    await expect(dialog.getByTestId('upload-error')).toContainText(
      'metadata.csv has changed or can no longer be read since it was selected, so nothing was uploaded. Select it again')
    await page.screenshot({ path: test.info().outputPath('upload-changed-csv.png') })

    await dialog.getByTestId('upload-metadata').setInputFiles(csv)
    await dialog.getByTestId('upload-submit').click()
    await expect(dialog.getByTestId('upload-results')).toContainText('The document was added.')
    await expect(dialog.getByTestId('upload-error')).toHaveCount(0)
  } finally {
    await collection.remove()
  }
})

test('a shared user is not offered the upload', async ({ page }) => {
  await useViewport(page, 'wide')
  await ensureLoggedIn(page, 'annotator')
  await page.goto(`/#/collections/${fixture.collection('chronicles').id}/documents`)
  await expect(page.getByText(fixture.document('letters').properties.title)).toBeVisible()
  await expect(page.getByTestId('upload-text-documents')).toHaveCount(0)
})
