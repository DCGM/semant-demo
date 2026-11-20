import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { Dialog, QBtn, QFile, Quasar } from 'quasar'
import { createMemoryHistory, createRouter } from 'vue-router'

import { ResponseError, type TextUploadAvailability, type TextUploadResponse } from 'src/generated/api'
import TextUploadDialog from 'src/features/documents/upload/TextUploadDialog.vue'
import { CSV_TEMPLATE, checkFiles, filesNotSaved, readSelection, summary } from 'src/features/documents/upload/textUpload'

// Upload of private text documents into a collection (#785): the client spares obviously
// invalid requests, shows every file's result with a link to each added document, offers to
// send again the files that failed, and reports a refused request without claiming success.

const uploaded = vi.fn<[string, File[], File | null], Promise<TextUploadResponse>>()
const availability = vi.fn<[], Promise<TextUploadAvailability>>()

vi.mock('src/features/documents/useDocumentsRepository', () => ({
  useDocumentsRepository: () => ({
    textUploadAvailability: () => availability(),
    uploadTextDocuments: (collectionId: string, files: File[], metadata: File | null) => uploaded(collectionId, files, metadata)
  })
}))

const txt = (name: string, content = 'Text.') => new File([content], name, { type: 'text/plain' })
/** A selected file whose content changed on disk afterwards: the browser refuses to read it. */
const changed = (name: string) => {
  const file = txt(name)
  file.arrayBuffer = () => Promise.reject(new DOMException('The file changed.', 'NotReadableError'))
  return file
}
const sent = async (files: File[]) => Promise.all(files.map(async f => [f.name, await f.text()]))

describe('client checks', () => {
  it('refuses what the server would refuse anyway', () => {
    const problems = checkFiles([txt('a.txt'), txt('b.pdf'), txt('a.txt'), txt('empty.txt', ''),
      new File(['x'.repeat(2_000_001)], 'big.txt')])
    expect(problems.get('b.pdf')).toMatch('Only .txt')
    expect(problems.get('a.txt')).toMatch('same name')
    expect(problems.get('empty.txt')).toMatch('empty')
    expect(problems.get('big.txt')).toMatch('larger than 2 MB')
    expect(checkFiles(Array.from({ length: 21 }, (_, i) => txt(`${i}.txt`))).get('')).toMatch('At most 20')
    expect(checkFiles([txt('Kronika.TXT'), txt('b.txt')]).size).toBe(0)
  })

  it('keeps every file that was not saved, never saved or unconfirmed ones', () => {
    const files = ['ok.txt', 'failed.txt', 'invalid.txt', 'unsent.txt', 'uncertain.txt'].map(n => txt(n))
    const response: TextUploadResponse = {
      errors: [],
      files: [
        { filename: 'ok.txt', status: 'completed', chunks: 1 },
        { filename: 'failed.txt', status: 'failed', chunks: 1 },
        { filename: 'invalid.txt', status: 'invalid', chunks: 0 },
        { filename: 'unsent.txt', status: 'not_written', chunks: 0 },
        { filename: 'uncertain.txt', status: 'uncertain', chunks: 1 }
      ]
    }
    expect(filesNotSaved(files, response).map(f => f.name)).toEqual(['failed.txt', 'invalid.txt', 'unsent.txt'])
    expect(summary(response)).toBe('1 of 5 documents were added.')
  })

  it('reads the selection now and names the files that cannot be read', async () => {
    const { copies, unreadable } = await readSelection([txt('a.txt', 'Alfa'), changed('b.txt'), txt('meta.csv', 'filename')])
    expect(await sent(copies)).toEqual([['a.txt', 'Alfa'], ['meta.csv', 'filename']])
    expect(unreadable.map(f => f.name)).toEqual(['b.txt'])
  })

  it('offers a template with the documented columns', () => {
    expect(CSV_TEMPLATE.split('\r\n')[0]).toBe('filename,title,author,yearIssued,language')
  })
})

describe('TextUploadDialog', () => {
  const mounted: VueWrapper[] = []
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/c/:collectionId/d/:documentId', name: 'documentDetailV1', component: { template: '<div />' } },
      { path: '/', component: { template: '<div />' } }]
  })

  async function open () {
    const wrapper = mount(TextUploadDialog as never, {
      props: { collectionId: 'c1' } as never,
      global: { plugins: [[Quasar, { plugins: { Dialog } }], router] },
      attachTo: document.body
    })
    mounted.push(wrapper)
    ;(wrapper.vm as unknown as { show: () => void }).show()
    await flushPromises()
    return wrapper
  }
  const choose = async (wrapper: VueWrapper, files: File[], metadata: File | null = null) => {
    const [filesInput, csvInput] = wrapper.findAllComponents(QFile)
    filesInput.vm.$emit('update:modelValue', files)
    csvInput.vm.$emit('update:modelValue', metadata)
    await flushPromises()
  }
  const button = (wrapper: VueWrapper, label: RegExp) => wrapper.findAllComponents(QBtn).find(b => label.test(String(b.props('label'))))
  const click = async (wrapper: VueWrapper, label: RegExp) => {
    await button(wrapper, label)!.trigger('click')
    await flushPromises()
  }
  const results = () => Array.from(document.querySelectorAll('[data-testid="upload-result"]')).map(e => e.textContent?.replace(/\s+/g, ' ').trim())

  beforeEach(() => {
    uploaded.mockReset()
    availability.mockReset().mockResolvedValue({ available: true })
    URL.createObjectURL = vi.fn(() => 'blob:template')
    URL.revokeObjectURL = vi.fn()
  })
  afterEach(() => {
    mounted.splice(0).forEach(w => w.unmount())
    document.body.innerHTML = ''
  })

  it('uploads the chosen files with the CSV and links each added document', async () => {
    const files = [txt('Kronika.txt'), txt('b.txt')]
    const csv = new File(['filename,title\nKronika.txt,Kronika obce\n'], 'meta.csv')
    uploaded.mockResolvedValue({
      errors: [],
      files: [{ filename: 'Kronika.txt', status: 'completed', documentId: 'd1', title: 'Kronika obce', chunks: 3 },
        { filename: 'b.txt', status: 'completed', documentId: 'd2', title: 'b', chunks: 1 }]
    })
    const wrapper = await open()
    await choose(wrapper, files, csv)
    await click(wrapper, /^Upload$/)

    const [collectionId, sentFiles, sentCsv] = uploaded.mock.calls[0]
    expect(collectionId).toBe('c1')
    expect(await sent(sentFiles)).toEqual([['Kronika.txt', 'Text.'], ['b.txt', 'Text.']])
    expect(await sent([sentCsv!])).toEqual([['meta.csv', 'filename,title\nKronika.txt,Kronika obce\n']])
    expect(document.querySelector('[data-testid="upload-results"]')?.textContent).toContain('All 2 documents were added.')
    expect(results()[0]).toContain('Kronika obce')
    expect(results()[0]).toContain('3 passages')
    const link = document.querySelector('[data-testid="upload-result"] a') as HTMLAnchorElement
    expect(link.getAttribute('href')).toContain('/c/c1/d/d1')
    expect(document.querySelector('[data-testid="upload-template"]')?.getAttribute('href')).toBe('blob:template')
    expect(button(wrapper, /^Upload$/)!.props('disable')).toBe(true)
  })

  it('shows every failure and keeps only the files not saved selected', async () => {
    const files = [txt('ok.txt'), txt('failed.txt')]
    const csv = new File(['filename,title\nok.txt,OK\nfailed.txt,F\n'], 'meta.csv')
    uploaded.mockResolvedValueOnce({
      errors: [],
      files: [{ filename: 'ok.txt', status: 'completed', documentId: 'd1', title: 'ok', chunks: 1 },
        { filename: 'failed.txt', status: 'failed', documentId: 'd2', chunks: 2, error: 'Not added to the collection: embedding failed.' }]
    }).mockResolvedValueOnce({
      errors: [],
      files: [{ filename: 'failed.txt', status: 'completed', documentId: 'd3', title: 'failed', chunks: 2 }]
    })
    const wrapper = await open()
    await choose(wrapper, files, csv)
    await click(wrapper, /^Upload$/)

    expect(document.querySelector('[data-testid="upload-results"]')?.textContent).toContain('1 of 2 documents were added.')
    expect(results()[1]).toContain('Failed')
    expect(results()[1]).toContain('embedding failed')
    // The CSV also names the saved file, which a second upload would not include.
    expect(document.querySelector('[data-testid="upload-next"]')?.textContent).toContain('rows for these files only')
    await click(wrapper, /^Upload$/)

    expect(uploaded.mock.calls[1][1].map(f => f.name)).toEqual(['failed.txt'])
    expect(uploaded.mock.calls[1][2]).toBeNull()
    expect(document.querySelector('[data-testid="upload-results"]')?.textContent).toContain('The document was added.')
    // Nothing is left to upload: the saved files cannot be sent twice.
    expect(button(wrapper, /^Upload$/)!.props('disable')).toBe(true)
  })

  it('reports a refused request without a result and keeps the selection', async () => {
    uploaded.mockRejectedValue(new ResponseError(new Response(JSON.stringify({ detail: 'Uploading documents is not enabled on this server.' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } })))
    const wrapper = await open()
    await choose(wrapper, [txt('a.txt')])
    await click(wrapper, /^Upload$/)

    expect(document.querySelector('[data-testid="upload-error"]')?.textContent).toContain('not enabled')
    expect(document.querySelector('[data-testid="upload-results"]')).toBeNull()
    expect(button(wrapper, /^Upload$/)!.props('disable')).toBe(false)
  })

  it('names a file changed since it was selected, sends nothing and asks for it again', async () => {
    const wrapper = await open()
    await choose(wrapper, [txt('a.txt'), changed('b.txt')], changed('meta.csv'))
    await click(wrapper, /^Upload$/)

    expect(uploaded).not.toHaveBeenCalled()
    expect(document.querySelector('[data-testid="upload-error"]')?.textContent).toContain(
      'b.txt, meta.csv have changed or can no longer be read since they were selected, so nothing was uploaded. Select them again')
    // Only the readable file stays selected; choosing the others again appends their current content.
    const [filesInput, csvInput] = wrapper.findAllComponents(QFile)
    expect((filesInput.props('modelValue') as File[]).map(f => f.name)).toEqual(['a.txt'])
    expect(csvInput.props('modelValue')).toBeNull()

    await choose(wrapper, [txt('a.txt'), txt('b.txt', 'Opraveno.')], txt('meta.csv', 'filename,language\nb.txt,ces\n'))
    uploaded.mockResolvedValue({ errors: [], files: [] })
    await click(wrapper, /^Upload$/)
    expect(await sent(uploaded.mock.calls[0][1])).toEqual([['a.txt', 'Text.'], ['b.txt', 'Opraveno.']])
  })

  it('says before any upload that the server cannot take one, and does not send', async () => {
    availability.mockResolvedValue({ available: false, message: 'Uploading documents is not available: the database does not support it yet.' })
    const wrapper = await open()
    expect(document.querySelector('[data-testid="upload-unavailable"]')?.textContent).toContain('the database does not support it yet')
    await choose(wrapper, [txt('a.txt')])
    expect(button(wrapper, /^Upload$/)!.props('disable')).toBe(true)
    expect(uploaded).not.toHaveBeenCalled()
  })

  it('leaves the upload to report a server whose availability did not answer', async () => {
    availability.mockRejectedValue(new Error('offline'))
    const wrapper = await open()
    await choose(wrapper, [txt('a.txt')])
    expect(document.querySelector('[data-testid="upload-unavailable"]')).toBeNull()
    expect(button(wrapper, /^Upload$/)!.props('disable')).toBe(false)
  })

  it('does not send a selection with an invalid file', async () => {
    const wrapper = await open()
    await choose(wrapper, [txt('a.txt'), txt('scan.pdf')])

    expect(document.querySelector('[data-testid="upload-local-problems"]')?.textContent).toContain('scan.pdf')
    expect(button(wrapper, /^Upload$/)!.props('disable')).toBe(true)
    expect(uploaded).not.toHaveBeenCalled()
  })
})
