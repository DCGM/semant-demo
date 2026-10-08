import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import { Quasar } from 'quasar'
import { createPinia, setActivePinia } from 'pinia'
import { ref } from 'vue'

import DocumentDetailLayout from 'src/pages/Collections/xjuric31/DocumentDetailLayout.vue'
import useAiAssistance from 'src/composables/useAiAssistance'
import { useTagSpansStore } from 'src/stores/tagSpansStore'

// The layout's data loading is not under test: these composables return empty state.
vi.mock('vue-router', () => ({ useRoute: () => ({ params: {}, query: {} }) }))
vi.mock('src/repositories/useTagSpansRepository', () => ({ useTagSpansRepository: () => ({}) }))
vi.mock('src/composables/useDocuments', () => ({
  default: () => ({ activeDocument: ref(null), loadDocument: vi.fn(async () => undefined) })
}))
vi.mock('src/composables/useCollections', () => ({
  default: () => ({ activeCollection: ref(null), loadCollection: vi.fn(async () => undefined) })
}))
vi.mock('src/composables/useTags', () => ({
  default: () => ({
    tags: ref([]), loading: ref(false), loadTagsByCollection: vi.fn(async () => undefined), createTag: vi.fn(), updateTag: vi.fn()
  })
}))
vi.mock('src/composables/dialogs/useTagsDialog', () => ({ default: () => ({ openTagsDialog: vi.fn() }) }))
vi.mock('src/shared/api', async () => ({
  ...(await vi.importActual<typeof import('src/shared/api')>('src/shared/api')),
  useApi: () => ({ default: {} })
}))

const encoder = new TextEncoder()
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

/** A streamed response that keeps delivering after abort (a read already under way). */
function lateStream (signal: AbortSignal) {
  let controller!: { enqueue (chunk: Uint8Array): void, close (): void }
  const body = new ReadableStream<Uint8Array>({ start (c) { controller = c } })
  return {
    signal,
    body,
    push: (line: object) => controller.enqueue(encoder.encode(JSON.stringify(line) + '\n')),
    close: () => controller.close()
  }
}

const lateResult = (chunkId: string) => ({
  event: 'result',
  chunk_id: chunkId,
  spans: [{ id: `late-${chunkId}`, chunkId, tagId: 't', start: 0, end: 3, type: 'auto' }],
  error: 'late failure',
  unsaved: 1
})

describe('DocumentDetailLayout AI cleanup', () => {
  let streams: ReturnType<typeof lateStream>[]
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    setActivePinia(createPinia())
    streams = []
    globalThis.fetch = vi.fn((_url: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => {
      const stream = lateStream(init?.signal as AbortSignal)
      streams.push(stream)
      return Promise.resolve({ ok: true, body: stream.body } as Response)
    })
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('aborts document-wide and selection runs on unmount and ignores their late events', async () => {
    const wrapper = shallowMount(DocumentDetailLayout, {
      props: { collectionId: 'c', documentId: 'd' },
      global: { plugins: [[Quasar, {}]], stubs: { RouterView: true, 'router-view': true } }
    })
    await flush()
    const ai = useAiAssistance()
    const store = useTagSpansStore()

    const documentRun = ai.run({ collectionId: 'c', documentId: 'd', tagIds: ['t'], mode: 'thorough' })
    const selectionRun = ai.runOnSelection({
      collectionId: 'c', documentId: 'd', chunkIds: ['x'], selectionStart: 0, selectionEnd: 3, tagIds: ['t']
    })
    await flush()
    expect([ai.isRunning.value, ai.isSelectionRunning.value]).toEqual([true, true])

    wrapper.unmount() // same props: no document/collection change triggered the reset

    expect(streams.map((s) => s.signal.aborted)).toEqual([true, true])
    expect([ai.isRunning.value, ai.isSelectionRunning.value]).toEqual([false, false])

    // Events that arrive after the abort (reads already under way) change nothing.
    streams[0].push(lateResult('chunk-1'))
    streams[0].push({ event: 'end', outcome: 'failed', saved: 0, rejected: 0, save_failures: 1, search_tag_failures: 0, provider_failures: 0 })
    streams[1].push(lateResult('x'))
    streams.forEach((s) => s.close())
    await documentRun
    expect(await selectionRun).toBeNull()

    expect(store.spansByChunkId).toEqual({})
    expect([ai.isRunning.value, ai.isSelectionRunning.value]).toEqual([false, false])
    expect([ai.lastError.value, ai.lastSelectionError.value, ai.lastStatus.value]).toEqual([null, null, null])
    expect([ai.processedChunkCount.value, ai.totalSpansAdded.value, ai.totalUnsaved.value]).toEqual([0, 0, 0])
  })
})
