import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Quasar } from 'quasar'
import { createPinia, setActivePinia } from 'pinia'

import AiAssistPanel from 'src/features/annotations/AiAssistPanel.vue'
import { useTagsStore } from 'src/features/annotations/tagsStore'
import useAiAssistance from 'src/features/annotations/useAiAssistance'

// A document run that would evaluate more than 50 chunks asks first (#408): thorough
// counts the document's chunks in the collection, optimized the selected tags times the
// backend's per-tag limit (from the document stats, not a frontend constant).

const tag = (id: string, name: string) => ({ id, name, color: '#000', shorthand: id, collectionId: 'c1' })
const stats = { chunksInCollection: 10, aiMaxChunksPerTag: 40 as number | undefined }
const dialogs: { message: string, ok: () => void, cancel: () => void }[] = []

vi.mock('src/features/annotations/useTagsRepository', () => ({
  useTagsRepository: () => ({ getAllByCollection: async () => [tag('t1', 'Person'), tag('t2', 'Place')] })
}))
vi.mock('src/features/annotations/useTagSpansRepository', () => ({ useTagSpansRepository: () => ({}) }))
vi.mock('src/shared/api', async () => ({
  ...(await vi.importActual<typeof import('src/shared/api')>('src/shared/api')),
  useApi: () => ({
    default: { getDocumentStatsApiUserCollectionsCollectionIdDocumentsDocumentIdStatsGet: async () => ({ ...stats }) }
  })
}))
vi.mock('quasar', async () => {
  const actual = await vi.importActual<typeof import('quasar')>('quasar')
  return {
    ...actual,
    useQuasar: () => ({
      notify: vi.fn(),
      dialog: (options: { message: string }) => {
        const dialog: (typeof dialogs)[number] = { message: options.message, ok: () => undefined, cancel: () => undefined }
        dialogs.push(dialog)
        const chain = {
          onOk: (fn: () => void) => { dialog.ok = fn; return chain },
          onCancel: (fn: () => void) => { dialog.cancel = fn; return chain }
        }
        return chain
      }
    })
  }
})

describe('confirmation before a large AI run', () => {
  const originalFetch = globalThis.fetch
  let requested: string[]

  beforeEach(async () => {
    setActivePinia(createPinia())
    await useTagsStore().fetchTagsByCollection('c1')
    dialogs.length = 0
    requested = []
    Object.assign(stats, { chunksInCollection: 10, aiMaxChunksPerTag: 40 })
    const end = JSON.stringify({ event: 'end', outcome: 'complete', saved: 0, rejected: 0, save_failures: 0, search_tag_failures: 0, provider_failures: 0 })
    globalThis.fetch = vi.fn((url: Parameters<typeof fetch>[0]) => {
      requested.push(String(url))
      return Promise.resolve(new Response(end + '\n'))
    })
  })

  afterEach(() => {
    useAiAssistance().reset()
    globalThis.fetch = originalFetch
  })

  async function runAi (tags: number, mode: 'optimized' | 'thorough' = 'optimized') {
    const wrapper = mount(AiAssistPanel, {
      props: { collectionId: 'c1', documentId: 'd1' },
      global: { plugins: [[Quasar, {}]] }
    })
    if (mode === 'thorough') await wrapper.findAll('.q-radio')[1].trigger('click')
    for (const checkbox of wrapper.findAll('.ai-tag-checkbox').slice(0, tags)) await checkbox.trigger('click')
    await wrapper.findAll('button').find((b) => b.text().includes('Run AI'))!.trigger('click')
    await flushPromises()
    return wrapper
  }

  it('asks before optimized tags times the per-tag limit exceed 50, and cancelling runs nothing', async () => {
    await runAi(2)

    expect(dialogs.map((d) => d.message)).toEqual([expect.stringMatching(/up to 80 chunks \(2 tag\(s\) × at most 40/)])
    dialogs[0].cancel()
    await flushPromises()
    expect(requested).toEqual([])
  })

  it('starts the run once confirmed', async () => {
    await runAi(2)
    dialogs[0].ok()
    await flushPromises()

    expect(requested).toEqual([expect.stringMatching(/\/ai\/suggest_spans\/optimized$/)])
  })

  it('starts small runs at once, using the backend limit', async () => {
    await runAi(1) // 1 × 40
    stats.aiMaxChunksPerTag = 20
    await runAi(2) // 2 × 20

    expect(dialogs).toEqual([])
    expect(requested).toHaveLength(2)
  })

  it('asks before a thorough run over more than 50 chunks only', async () => {
    stats.chunksInCollection = 50
    await runAi(2, 'thorough')
    stats.chunksInCollection = 51
    await runAi(2, 'thorough')

    expect(dialogs.map((d) => d.message)).toEqual([expect.stringMatching(/all 51 chunks/)])
    expect(requested).toEqual([expect.stringMatching(/\/ai\/suggest_spans\/thorough$/)])
  })
})
