import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Quasar } from 'quasar'
import { createPinia, setActivePinia } from 'pinia'
import { routeLocationKey, routerKey } from 'vue-router'

import type { Collection, DocumentStats } from 'src/generated/api'
import DocumentsTable from 'src/features/documents/DocumentsTable.vue'
import { bulkRemovalConfirmation, singleRemovalConfirmation } from 'src/features/documents/removalConfirmation'
import { useUserCollectionsStore } from 'src/features/user_collections/userCollectionsStore'
import { useDocumentsStore } from 'src/features/documents/documentsStore'
import * as documentsRepositoryModule from 'src/features/documents/useDocumentsRepository'
import * as quasarModule from 'quasar'

type Spy = ReturnType<typeof vi.fn>
const { repo } = documentsRepositoryModule as unknown as {
  repo: { removeFromCollection: Spy, getAllByCollection: Spy, getStats: Spy }
}
// The dialogs the page opened: their options, `confirm` to press OK and `cancel` to press
// Cancel (runs the onCancel and onDismiss handlers, as Quasar does).
interface OpenedDialog { options: Record<string, unknown>, confirm: () => void, cancel: () => void }
const { dialogs } = quasarModule as unknown as { dialogs: { opened: OpenedDialog[] } }

vi.mock('quasar', async () => {
  const quasar = await vi.importActual<typeof import('quasar')>('quasar')
  const dialogs: { opened: unknown[] } = { opened: [] }
  return {
    ...quasar,
    dialogs,
    useQuasar: () => ({
      ...quasar.useQuasar(),
      dialog: (options: Record<string, unknown>) => {
        const handlers: Record<'ok' | 'cancel' | 'dismiss', (() => void)[]> = { ok: [], cancel: [], dismiss: [] }
        const run = (...kinds: (keyof typeof handlers)[]) => { for (const k of kinds) handlers[k].forEach((fn) => fn()) }
        dialogs.opened.push({ options, confirm: () => run('ok', 'dismiss'), cancel: () => run('cancel', 'dismiss') })
        const chain = {
          onOk: (fn: () => void) => { handlers.ok.push(fn); return chain },
          onCancel: (fn: () => void) => { handlers.cancel.push(fn); return chain },
          onDismiss: (fn: () => void) => { handlers.dismiss.push(fn); return chain }
        }
        return chain
      },
      notify: vi.fn()
    })
  }
})
vi.mock('src/shared/notification', () => {
  const notif = { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() }
  return { ongoingNotification: () => notif, warningNotification: vi.fn(), notif }
})
vi.mock('src/features/documents/useBrowseLibraryDialog', () => ({ default: () => ({ openBrowseLibraryDialog: vi.fn() }) }))
vi.mock('src/features/documents/useDocumentsRepository', () => {
  const repo = { removeFromCollection: vi.fn(), getAllByCollection: vi.fn(), getStats: vi.fn() }
  return { useDocumentsRepository: () => repo, repo }
})

const stats = (documentId: string, annotationsCount: number, suggestionsCount = 0, collectionId = 'col-1'): DocumentStats => ({
  documentId,
  collectionId,
  chunksInCollection: 1,
  totalChunks: 1,
  annotationsCount,
  distinctTagsCount: annotationsCount ? 1 : 0,
  suggestionsCount
})

describe('singleRemovalConfirmation', () => {
  it('keeps the plain confirmation for a document without annotations', () => {
    expect(singleRemovalConfirmation({ title: 'First', stats: stats('d1', 0) })).toEqual({
      title: 'Remove Document',
      message: 'Remove the document "First" from the collection?',
      okLabel: 'Remove'
    })
  })

  it('asks and names the confirmed annotations and suggestions of the document', () => {
    const { title, message } = singleRemovalConfirmation({ title: 'First', stats: stats('d1', 5, 1) })
    expect(title).toBe('Remove Annotated Document')
    expect(message).toBe(
      'Remove the document "First" from the collection? ' +
      'It has 5 confirmed annotations and 1 pending AI suggestion in this collection. ' +
      'They are not deleted, but the document cannot be opened in this collection until it is added back.'
    )
  })

  it('warns about pending AI suggestions alone', () => {
    const { title, message } = singleRemovalConfirmation({ title: 'First', stats: stats('d1', 0, 3) })
    expect(title).toBe('Remove Document')
    expect(message).toContain('Remove the document "First" from the collection? It has 3 pending AI suggestions in this collection.')
  })

  it('refers to a single annotation in the singular', () => {
    expect(singleRemovalConfirmation({ title: 'First', stats: stats('d1', 0, 1) }).message).toBe(
      'Remove the document "First" from the collection? It has 1 pending AI suggestion in this collection. ' +
      'It is not deleted, but the document cannot be opened in this collection until it is added back.'
    )
  })

  it('treats unavailable stats as unknown, not as no annotations', () => {
    const { message } = singleRemovalConfirmation({ title: 'First', stats: undefined })
    expect(message).toContain('Its annotation count could not be loaded.')
    expect(message).not.toMatch(/no annotations/i)
  })

  it('says the count is still loading rather than failed while stats load', () => {
    expect(singleRemovalConfirmation({ title: 'First', stats: null, loading: true }).message)
      .toContain('Its annotation count is still loading.')
  })

  it('never says that annotations are deleted', () => {
    for (const s of [stats('d1', 0), stats('d1', 2, 2), undefined]) {
      expect(singleRemovalConfirmation({ title: 'First', stats: s }).message).not.toMatch(/will be deleted/i)
    }
  })
})

describe('bulkRemovalConfirmation', () => {
  it('keeps the plain confirmation when no selected document has annotations', () => {
    expect(bulkRemovalConfirmation([{ title: 'A', stats: stats('a', 0) }, { title: 'B', stats: stats('b', 0) }])).toEqual({
      title: 'Remove Selected Documents',
      message: 'Remove 2 selected documents from the collection?',
      okLabel: 'Remove selected'
    })
  })

  it('totals the annotated documents and counts the unknown ones separately', () => {
    const { title, message } = bulkRemovalConfirmation([
      { title: 'A', stats: stats('a', 4) },
      { title: 'B', stats: stats('b', 1, 2) },
      { title: 'C', stats: stats('c', 0) },
      { title: 'D', stats: null }
    ])
    expect(title).toBe('Remove Annotated Documents')
    expect(message).toBe(
      'Remove 4 selected documents from the collection? ' +
      '2 of them have 5 confirmed annotations and 2 pending AI suggestions in this collection between them. ' +
      'The annotation count of 1 document could not be loaded. ' +
      'Annotations are not deleted, but a removed document cannot be opened in this collection until it is added back.'
    )
  })

  it('names only pending AI suggestions when no selected document has confirmed annotations', () => {
    const { title, message } = bulkRemovalConfirmation([
      { title: 'A', stats: stats('a', 0, 3) },
      { title: 'B', stats: stats('b', 0) }
    ])
    expect(title).toBe('Remove Selected Documents')
    expect(message).toContain('1 of them has 3 pending AI suggestions in this collection.')
    expect(message).not.toContain('confirmed')
  })

  it('gives one selected document the single-document confirmation', () => {
    const target = { title: 'A', stats: stats('a', 2) }
    expect(bulkRemovalConfirmation([target])).toEqual(singleRemovalConfirmation(target))
  })

  it('says the counts are still loading while stats load', () => {
    expect(bulkRemovalConfirmation([{ title: 'A', loading: true }, { title: 'B', loading: true }]).message)
      .toContain('The annotation count of 2 documents is still loading.')
  })
})

describe('DocumentsTable removal', () => {
  const quasar = {
    plugins: [[Quasar, {}]] as never,
    provide: {
      [routeLocationKey as symbol]: { params: { collectionId: 'col-1' }, query: {} },
      [routerKey as symbol]: { push: () => undefined }
    }
  }
  const owned = { id: 'col-1', name: 'Chronicles', owner: 'Owner', isSharedWithMe: false } as Collection

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    dialogs.opened = []
    // A new list per fetch, as from the API: the table reloads the stats when the list is replaced.
    repo.getAllByCollection.mockImplementation(async () => [{ id: 'd1', title: 'First' }, { id: 'd2', title: 'Second' }])
    // d2's stats fail to load.
    repo.getStats.mockImplementation(async (_c: string, id: string) => {
      if (id === 'd2') throw new Error('stats failed')
      return stats(id, 5)
    })
    repo.removeFromCollection.mockResolvedValue({ outcome: 'complete' })
  })

  // Unmounted after each test, also a failed one, so no teleported button is left in the body.
  let wrapper: ReturnType<typeof mount> | null = null
  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
  })

  async function mountTable () {
    useUserCollectionsStore().activeCollection = owned
    wrapper = mount(DocumentsTable, { global: quasar, attachTo: document.body })
    await flushPromises()
    return wrapper
  }

  const removeButton = (wrapper: ReturnType<typeof mount>, row: number) =>
    wrapper.findAll('tbody tr')[row].find('button[aria-label="Remove document from collection"]')

  it('warns about the annotations and removes nothing on cancel', async () => {
    const wrapper = await mountTable()

    await removeButton(wrapper, 0).trigger('click')
    expect(dialogs.opened).toHaveLength(1)
    expect(dialogs.opened[0].options.title).toBe('Remove Annotated Document')
    expect(dialogs.opened[0].options.message).toContain('It has 5 confirmed annotations in this collection.')
    dialogs.opened[0].cancel()
    await flushPromises()
    expect(repo.removeFromCollection).not.toHaveBeenCalled()
  })

  it('removes the document through the existing flow on confirm', async () => {
    const wrapper = await mountTable()

    await removeButton(wrapper, 0).trigger('click')
    dialogs.opened[0].confirm()
    await flushPromises()
    expect(repo.removeFromCollection).toHaveBeenCalledWith('d1', 'col-1')
  })

  it('treats the stats as unavailable while they reload', async () => {
    const wrapper = await mountTable()
    // The next load never finishes: the map still holds the previous load's stats.
    repo.getStats.mockImplementation(() => new Promise(() => undefined))
    void useDocumentsStore().fetchDocumentsByCollection('col-1')
    await flushPromises()

    await removeButton(wrapper, 0).trigger('click')
    expect(dialogs.opened[0].options.title).toBe('Remove Document')
    expect(dialogs.opened[0].options.message).toContain('Its annotation count is still loading.')
    expect(dialogs.opened[0].options.message).not.toContain('5 confirmed annotations')
  })

  it('ignores stats of another collection', async () => {
    repo.getStats.mockImplementation(async (_c: string, id: string) => stats(id, 5, 0, 'col-2'))
    const wrapper = await mountTable()

    await removeButton(wrapper, 0).trigger('click')
    expect(dialogs.opened[0].options.message).toContain('Its annotation count could not be loaded.')
    expect(dialogs.opened[0].options.message).not.toContain('5 confirmed annotations')
  })

  it('reports a document whose stats failed as unknown in the bulk confirmation', async () => {
    const wrapper = await mountTable()

    const rows = wrapper.findAll('tbody tr')
    await rows[0].find('.q-checkbox').trigger('click')
    await rows[1].find('.q-checkbox').trigger('click')
    Array.from(document.body.querySelectorAll('button')).find((b) => b.textContent?.includes('Remove selected'))!.click()
    await flushPromises()

    expect(dialogs.opened[0].options.message).toContain('1 of them has 5 confirmed annotations in this collection.')
    expect(dialogs.opened[0].options.message).toContain('The annotation count of 1 document could not be loaded.')
    expect(repo.removeFromCollection).not.toHaveBeenCalled()

    dialogs.opened[0].confirm()
    await flushPromises()
    expect(repo.removeFromCollection.mock.calls.map((c) => c[0])).toEqual(['d1', 'd2'])
  })
})
