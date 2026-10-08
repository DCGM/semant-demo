import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Quasar } from 'quasar'
import { createPinia, setActivePinia } from 'pinia'
import { routeLocationKey, routerKey } from 'vue-router'

import type { Collection } from 'src/generated/api'
import { collectionRights } from 'src/features/collections/permissions'
import CollectionCard from 'src/components/custom/CollectionCard.vue'
import CollectionMembersPage from 'src/pages/Collections/CollectionMembersPage.vue'
import DocumentsTable from 'src/components/tables/DocumentsTable.vue'
import { useCollectionsStore } from 'src/stores/collectionsStore'
import * as notificationModule from 'src/utils/notification'
import * as documentsRepositoryModule from 'src/repositories/useDocumentsRepository'

type Spy = ReturnType<typeof vi.fn>
const { notif } = notificationModule as unknown as { notif: { error: Spy } }
const { repo } = documentsRepositoryModule as unknown as { repo: { removeFromCollection: Spy, getAllByCollection: Spy } }

// Confirmation dialogs are accepted at once.
vi.mock('quasar', async () => {
  const quasar = await vi.importActual<typeof import('quasar')>('quasar')
  return {
    ...quasar,
    useQuasar: () => ({
      ...quasar.useQuasar(),
      dialog: () => ({ onOk: (ok: () => void) => { ok() } }),
      notify: vi.fn()
    })
  }
})

// The mocked modules export their spies (`notif`, `repo`) for the assertions.
vi.mock('src/utils/notification', () => {
  const notif = { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() }
  return { ongoingNotification: () => notif, warningNotification: vi.fn(), notif }
})
vi.mock('src/repositories/useCollectionRepository', () => ({
  useCollectionRepository: () => ({
    getMembers: async () => [{ id: 'u2', username: 'annotator', name: 'Ann Otator' }]
  })
}))
vi.mock('src/repositories/useUserRepository', () => ({ useUserRepository: () => ({ search: async () => [] }) }))
vi.mock('src/repositories/useDocumentsRepository', () => {
  const repo = { removeFromCollection: vi.fn(), getAllByCollection: vi.fn(), getStats: async () => null }
  return { useDocumentsRepository: () => repo, repo }
})

const collection = (isSharedWithMe: boolean): Collection => ({
  id: 'col-1',
  name: 'Chronicles',
  owner: 'Owner Name',
  createdAt: new Date('2026-01-01'),
  updatedAt: new Date('2026-01-02'),
  color: '#123456',
  isSharedWithMe
})

// The page reads its collection id from the route (useRoute injects it).
const quasar = {
  plugins: [[Quasar, {}]] as never,
  provide: {
    [routeLocationKey as symbol]: { params: { collectionId: 'col-1' }, query: {} },
    [routerKey as symbol]: { push: () => undefined }
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('collectionRights', () => {
  it('grants shared users annotation, tag and member-list rights only', () => {
    expect(collectionRights(collection(true))).toEqual({
      annotate: true, editTags: true, viewMembers: true, editMembership: false, editMetadata: false, share: false
    })
    expect(collectionRights(collection(false))).toEqual({
      annotate: true, editTags: true, viewMembers: true, editMembership: true, editMetadata: true, share: true
    })
  })

  it('grants nothing for a collection that is not loaded', () => {
    expect(Object.values(collectionRights(null)).some(Boolean)).toBe(false)
  })
})

describe('CollectionCard', () => {
  const labels = (wrapper: ReturnType<typeof mount>) =>
    wrapper.findAll('button[aria-label]').map((b) => b.attributes('aria-label'))

  it('shows share, edit and delete to the owner', () => {
    const wrapper = mount(CollectionCard, { props: { collection: collection(false) }, global: quasar })
    expect(labels(wrapper)).toEqual(['Share collection', 'Edit collection', 'Delete collection'])
  })

  it('hides them from a shared user', () => {
    const wrapper = mount(CollectionCard, { props: { collection: collection(true) }, global: quasar })
    expect(labels(wrapper)).toEqual([])
    expect(wrapper.text()).toContain('Shared by Owner Name')
  })
})

describe('CollectionMembersPage', () => {
  async function mountFor (isSharedWithMe: boolean) {
    useCollectionsStore().activeCollection = collection(isSharedWithMe)
    const wrapper = mount(CollectionMembersPage, { global: quasar })
    await flushPromises()
    return wrapper
  }

  it('lets a shared user see the members but not share or unshare', async () => {
    const wrapper = await mountFor(true)

    expect(wrapper.text()).toContain('Ann Otator')
    expect(wrapper.text()).not.toContain('Share with a user')
    expect(wrapper.find('button[aria-label="Cancel share"]').exists()).toBe(false)
  })

  it('lets the owner share and unshare', async () => {
    const wrapper = await mountFor(false)

    expect(wrapper.text()).toContain('Share with a user')
    expect(wrapper.find('button[aria-label="Cancel share"]').exists()).toBe(true)
  })
})

describe('DocumentsTable', () => {
  const documents = [{ id: 'd1', title: 'First' }, { id: 'd2', title: 'Second' }, { id: 'd3', title: 'Third' }]

  async function mountFor (isSharedWithMe: boolean) {
    repo.getAllByCollection.mockResolvedValue(documents)
    useCollectionsStore().activeCollection = collection(isSharedWithMe)
    const wrapper = mount(DocumentsTable, { global: quasar, attachTo: document.body })
    await flushPromises()
    return wrapper
  }

  const titles = (wrapper: ReturnType<typeof mount>) =>
    wrapper.findAll('tbody tr').map((row) => row.text()).map((t) => documents.find((d) => t.includes(d.title))?.id)

  it('offers a shared user no way to add or remove documents', async () => {
    const wrapper = await mountFor(true)

    expect(titles(wrapper)).toEqual(['d1', 'd2', 'd3'])
    expect(wrapper.text()).not.toContain('Add Document')
    expect(wrapper.find('button[aria-label="Remove document from collection"]').exists()).toBe(false)
    expect(wrapper.find('tbody .q-checkbox').exists()).toBe(false)
    wrapper.unmount()
  })

  it('removes only the documents whose removal was acknowledged and reports the rest', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const wrapper = await mountFor(false)
    expect(wrapper.text()).toContain('Add Document')
    repo.removeFromCollection.mockImplementation(async (documentId: string) => {
      if (documentId === 'd2') throw new Error('storage failed')
      return { outcome: 'complete' }
    })

    const rows = wrapper.findAll('tbody tr')
    await rows[0].find('.q-checkbox').trigger('click')
    await rows[1].find('.q-checkbox').trigger('click')
    const removeSelected = Array.from(document.body.querySelectorAll('button'))
      .find((b) => b.textContent?.includes('Remove selected'))!
    removeSelected.click()
    await flushPromises()

    expect(repo.removeFromCollection.mock.calls.map((c) => c[0])).toEqual(['d1', 'd2'])
    expect(titles(wrapper)).toEqual(['d2', 'd3'])
    expect(notif.error).toHaveBeenCalledWith('Removed 1 of 2 documents. The others could not be removed.')
    wrapper.unmount()
  })
})
