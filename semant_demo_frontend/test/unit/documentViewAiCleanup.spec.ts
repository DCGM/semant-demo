import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, shallowMount } from '@vue/test-utils'
import { Quasar } from 'quasar'
import { createPinia, setActivePinia } from 'pinia'

import DocumentViewLayout from 'src/features/documents/viewer/DocumentViewLayout.vue'
import { useRightSidebarStore } from 'src/app/sidebar/rightSidebarStore'
import useAiAssistance from 'src/features/annotations/useAiAssistance'
import { useTagSpansStore } from 'src/features/annotations/tagSpansStore'

// The layout's data loading is not under test: the stores load empty state.
vi.mock('vue-router', () => ({ useRoute: () => ({ params: {}, query: {} }) }))
vi.mock('src/features/annotations/useTagSpansRepository', () => ({ useTagSpansRepository: () => ({}) }))
vi.mock('src/features/documents/useDocumentsRepository', () => ({ useDocumentsRepository: () => ({ getById: async () => null }) }))
vi.mock('src/features/user_collections/useUserCollectionsRepository', () => ({
  useUserCollectionsRepository: () => ({ getById: async () => null })
}))
vi.mock('src/features/annotations/useTagsRepository', () => ({ useTagsRepository: () => ({ getAllByCollection: async () => [] }) }))
vi.mock('src/features/annotations/useTagsDialog', () => ({ default: () => ({ openTagsDialog: vi.fn() }) }))
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

describe('DocumentViewLayout AI cleanup', () => {
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
    const wrapper = shallowMount(DocumentViewLayout, {
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

describe('DocumentViewLayout sidebar panels', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  function mountLayout () {
    // The real layout and panel wrappers register in the sidebar; the tools are stubbed.
    return mount(DocumentViewLayout, {
      props: { collectionId: 'c', documentId: 'd' },
      global: {
        plugins: [[Quasar, {}]],
        stubs: {
          RouterView: true,
          QBtn: true,
          DocumentTagsPanel: true,
          AiAssistPanel: true,
          DocumentSummaryPanel: true,
          DocumentMetadataPanel: true
        }
      }
    })
  }

  const ctrlF = () => {
    const event = new KeyboardEvent('keydown', { key: 'f', ctrlKey: true, cancelable: true })
    window.dispatchEvent(event)
    return event
  }

  it('registers the tools and shows auto spans only while the AI assist panel is active', async () => {
    const wrapper = mountLayout()
    await flush()
    const sidebar = useRightSidebarStore()
    const ai = useAiAssistance()
    expect(sidebar.sortedPanels.map((p) => p.label)).toEqual(['Tags', 'AI assist', 'Summary', 'Document'])
    expect([sidebar.activePanel?.label, ai.aiPanelActive.value]).toEqual(['Tags', false])

    sidebar.activate('document-ai')
    await flush()
    expect(ai.aiPanelActive.value).toBe(true)
    ai.highlightedAutoSpanId.value = 'span-1'

    sidebar.activate('document-metadata')
    await flush()
    expect([ai.aiPanelActive.value, ai.highlightedAutoSpanId.value]).toEqual([false, null])

    sidebar.activate('document-ai')
    await flush()
    wrapper.unmount()
    expect([sidebar.hasPanels, ai.aiPanelActive.value]).toEqual([false, false])
  })

  it('takes Ctrl+F for the tag search only while the Tags panel is active', async () => {
    const wrapper = mountLayout()
    await flush()
    const sidebar = useRightSidebarStore()
    sidebar.open = false

    expect(ctrlF().defaultPrevented).toBe(true)
    expect(sidebar.open).toBe(true) // the closed sidebar opens on the search

    sidebar.activate('document-ai')
    expect(ctrlF().defaultPrevented).toBe(false) // the browser's find

    wrapper.unmount()
    expect(ctrlF().defaultPrevented).toBe(false)
  })
})
