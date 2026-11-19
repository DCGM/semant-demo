import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Quasar } from 'quasar'
import { createPinia, setActivePinia } from 'pinia'
import { routeLocationKey, routerKey } from 'vue-router'

import type { Collection, DocumentStats } from 'src/generated/api'
import DocumentsTable from 'src/features/documents/DocumentsTable.vue'
import { bulkRemovalConfirmation, singleRemovalConfirmation } from 'src/features/documents/removalConfirmation'
import { useUserCollectionsStore } from 'src/features/user_collections/userCollectionsStore'
import * as documentsRepositoryModule from 'src/features/documents/useDocumentsRepository'
import * as quasarModule from 'quasar'

type Spy = ReturnType<typeof vi.fn>
const { repo } = documentsRepositoryModule as unknown as {
  repo: { removeFromCollection: Spy, getAllByCollection: Spy, getStats: Spy }
}
// The last dialog the page opened: its options, and `confirm` to press OK. Not pressing it is Cancel.
const { dialogs } = quasarModule as unknown as { dialogs: { opened: { options: Record<string, unknown>, confirm: () => void }[] } }

vi.mock('quasar', async () => {
  const quasar = await vi.importActual<typeof import('quasar')>('quasar')
  const dialogs: { opened: unknown[] } = { opened: [] }
  return {
    ...quasar,
    dialogs,
    useQuasar: () => ({
      ...quasar.useQuasar(),
      dialog: (options: Record<string, unknown>) => {
        let ok: () => void = () => undefined
        dialogs.opened.push({ options, confirm: () => ok() })
        return { onOk: (fn: () => void) => { ok = fn } }
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

const stats = (documentId: string, annotationsCount: number, suggestionsCount = 0): DocumentStats => ({
  documentId,
  collectionId: 'col-1',
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

  it('names the confirmed annotations and suggestions the collection stops showing', () => {
    const { title, message } = singleRemovalConfirmation({ title: 'First', stats: stats('d1', 5, 1) })
    expect(title).toBe('Remove Annotated Document')
    expect(message).toBe(
      '"First" has 5 confirmed annotations and 1 pending AI suggestion in this collection. ' +
      'Removing it from the collection hides them here. They are not deleted: they show again if the document is added back.'
    )
  })

  it('warns about pending AI suggestions alone', () => {
    const { title, message } = singleRemovalConfirmation({ title: 'First', stats: stats('d1', 0, 3) })
    expect(title).toBe('Remove Document')
    expect(message).toContain('"First" has 3 pending AI suggestions in this collection.')
  })

  it('refers to a single annotation in the singular', () => {
    expect(singleRemovalConfirmation({ title: 'First', stats: stats('d1', 0, 1) }).message).toBe(
      '"First" has 1 pending AI suggestion in this collection. ' +
      'Removing it from the collection hides it here. It is not deleted: it shows again if the document is added back.'
    )
  })

  it('treats unavailable stats as unknown, not as no annotations', () => {
    const { message } = singleRemovalConfirmation({ title: 'First', stats: undefined })
    expect(message).toContain('Its annotation count could not be loaded.')
    expect(message).not.toMatch(/no annotations/i)
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
      '2 of them have annotations in this collection (5 confirmed annotations and 2 pending AI suggestions in total), ' +
      'which removing hides here. The annotation count of 1 document could not be loaded. ' +
      'Annotations are not deleted: they show again if a document is added back.'
    )
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
    repo.getAllByCollection.mockResolvedValue([{ id: 'd1', title: 'First' }, { id: 'd2', title: 'Second' }])
    // d2's stats fail to load.
    repo.getStats.mockImplementation(async (_c: string, id: string) => {
      if (id === 'd2') throw new Error('stats failed')
      return stats(id, 5)
    })
    repo.removeFromCollection.mockResolvedValue({ outcome: 'complete' })
  })

  async function mountTable () {
    useUserCollectionsStore().activeCollection = owned
    const wrapper = mount(DocumentsTable, { global: quasar, attachTo: document.body })
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
    expect(dialogs.opened[0].options.message).toContain('"First" has 5 confirmed annotations in this collection.')
    await flushPromises()
    expect(repo.removeFromCollection).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('removes the document through the existing flow on confirm', async () => {
    const wrapper = await mountTable()

    await removeButton(wrapper, 0).trigger('click')
    dialogs.opened[0].confirm()
    await flushPromises()
    expect(repo.removeFromCollection).toHaveBeenCalledWith('d1', 'col-1')
    wrapper.unmount()
  })

  it('reports a document whose stats failed as unknown in the bulk confirmation', async () => {
    const wrapper = await mountTable()

    const rows = wrapper.findAll('tbody tr')
    await rows[0].find('.q-checkbox').trigger('click')
    await rows[1].find('.q-checkbox').trigger('click')
    Array.from(document.body.querySelectorAll('button')).find((b) => b.textContent?.includes('Remove selected'))!.click()
    await flushPromises()

    expect(dialogs.opened[0].options.message).toContain('1 of them has annotations in this collection (5 confirmed annotations in total)')
    expect(dialogs.opened[0].options.message).toContain('The annotation count of 1 document could not be loaded.')
    expect(repo.removeFromCollection).not.toHaveBeenCalled()

    dialogs.opened[0].confirm()
    await flushPromises()
    expect(repo.removeFromCollection.mock.calls.map((c) => c[0])).toEqual(['d1', 'd2'])
    wrapper.unmount()
  })
})
