import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { readNdjson } from 'src/shared/api'
import useAiAssistance, { describeRunEnd } from 'src/composables/useAiAssistance'
import { useTagSpansStore } from 'src/stores/tagSpansStore'

vi.mock('src/repositories/useTagSpansRepository', () => ({ useTagSpansRepository: () => ({}) }))

const encoder = new TextEncoder()

/** A response body the test writes to; `ignoreAbort` simulates a read already under way. */
function controlledStream (signal?: AbortSignal, ignoreAbort = false) {
  let controller!: { enqueue (chunk: Uint8Array): void, error (e: unknown): void, close (): void }
  const body = new ReadableStream<Uint8Array>({ start (c) { controller = c } })
  if (signal && !ignoreAbort) {
    signal.addEventListener('abort', () => controller.error(Object.assign(new Error('aborted'), { name: 'AbortError' })))
  }
  return {
    body,
    push: (text: string) => controller.enqueue(encoder.encode(text)),
    pushBytes: (bytes: Uint8Array) => controller.enqueue(bytes),
    close: () => controller.close()
  }
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

const span = (id: string, chunkId: string) => ({ id, chunkId, tagId: 't', start: 0, end: 3, type: 'auto' })
const result = (chunkId: string, ids: string[], extra = {}) =>
  JSON.stringify({ event: 'result', chunk_id: chunkId, spans: ids.map((id) => span(id, chunkId)), error: null, unsaved: 0, ...extra }) + '\n'
const end = (outcome: string, extra = {}) =>
  JSON.stringify({
    event: 'end', outcome, saved: 0, rejected: 0, save_failures: 0, search_tag_failures: 0, provider_failures: 0, error: null, ...extra
  }) + '\n'

describe('readNdjson', () => {
  it('joins lines split across chunks, also inside a UTF-8 character', async () => {
    const stream = controlledStream()
    const values: unknown[] = []
    const invalid: string[] = []
    const done = readNdjson(stream.body, (v) => values.push(v), (line) => invalid.push(line))
    const bytes = encoder.encode('{"a":"Novák 😀"}\n\nnot json\n{"b":')
    const cut = bytes.indexOf(0xf0) + 2 // inside the emoji's four bytes
    stream.pushBytes(bytes.slice(0, cut))
    stream.pushBytes(bytes.slice(cut))
    stream.push('1}')
    stream.close()
    await done

    expect(values).toEqual([{ a: 'Novák 😀' }, { b: 1 }])
    expect(invalid).toEqual(['not json'])
  })
})

describe('useAiAssistance', () => {
  let streams: ReturnType<typeof controlledStream>[]
  let ignoreAbort: boolean
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    setActivePinia(createPinia())
    streams = []
    ignoreAbort = false
    globalThis.fetch = vi.fn((_url: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => {
      const stream = controlledStream(init?.signal ?? undefined, ignoreAbort)
      streams.push(stream)
      return Promise.resolve({ ok: true, body: stream.body } as Response)
    })
  })

  afterEach(() => {
    useAiAssistance().reset()
    globalThis.fetch = originalFetch
  })

  const request = (documentId: string) => ({ collectionId: 'c', documentId, tagIds: ['t'], mode: 'thorough' as const })

  it('shows saved spans as they arrive and reports a complete run', async () => {
    const ai = useAiAssistance()
    const store = useTagSpansStore()
    const running = ai.run(request('d1'))
    await flush()

    streams[0].push(result('chunk-1', ['s1']))
    await flush()
    expect(store.spansByChunkId['chunk-1'].map((s) => s.id)).toEqual(['s1'])
    expect(ai.isRunning.value).toBe(true)

    streams[0].push(end('complete', { saved: 1 }))
    streams[0].close()
    await running
    expect([ai.lastStatus.value, ai.lastError.value, ai.isRunning.value]).toEqual(['complete', null, false])
  })

  it('treats a stream without its end line as interrupted', async () => {
    const ai = useAiAssistance()
    const running = ai.run(request('d1'))
    await flush()

    streams[0].push(result('chunk-1', ['s1']))
    streams[0].close()
    await running

    expect(ai.lastStatus.value).toBe('interrupted')
    expect(ai.lastError.value).toMatch(/stopped before completion. Suggestions saved so far are kept/)
  })

  it('reports a partial run with its failures', async () => {
    const ai = useAiAssistance()
    const running = ai.run(request('d1'))
    await flush()

    streams[0].push(end('partial', { saved: 2, provider_failures: 1 }))
    streams[0].close()
    await running

    expect(ai.lastStatus.value).toBe('partial')
    expect(ai.lastError.value).toBe('AI suggestions were only partly completed (2 saved): 1 AI request(s) failed.')
  })

  it('ignores late events of a run started for another document', async () => {
    ignoreAbort = true // the old run's read was already under way when the user switched
    const ai = useAiAssistance()
    const store = useTagSpansStore()
    const old = ai.run(request('d1'))
    await flush()

    ai.reset() // document changed
    const current = ai.run(request('d2'))
    await flush()
    streams[0].push(result('old-chunk', ['old'], { error: 'old failure' }))
    streams[0].push(end('failed'))
    streams[0].close()
    await old

    expect(store.spansByChunkId['old-chunk']).toBeUndefined()
    expect([ai.isRunning.value, ai.lastError.value, ai.lastStatus.value]).toEqual([true, null, null])
    expect(ai.processedChunkCount.value).toBe(0)

    streams[1].push(result('new-chunk', ['new']))
    streams[1].push(end('complete', { saved: 1 }))
    streams[1].close()
    await current
    expect(store.spansByChunkId['new-chunk'].map((s) => s.id)).toEqual(['new'])
    expect([ai.isRunning.value, ai.lastStatus.value]).toEqual([false, 'complete'])
  })

  it('returns null for a selection run superseded by a context change', async () => {
    ignoreAbort = true
    const ai = useAiAssistance()
    const store = useTagSpansStore()
    const selection = ai.runOnSelection({
      collectionId: 'c', documentId: 'd1', chunkIds: ['x'], selectionStart: 0, selectionEnd: 3, tagIds: ['t']
    })
    await flush()

    ai.reset()
    streams[0].push(result('x', ['late'], { error: 'late failure' }))
    streams[0].close()

    expect(await selection).toBeNull()
    expect(store.spansByChunkId.x).toBeUndefined()
    expect(ai.lastSelectionError.value).toBeNull()
  })

  it('reports a cancelled run without an error', async () => {
    const ai = useAiAssistance()
    const running = ai.run(request('d1'))
    await flush()

    ai.cancel()
    await running

    expect([ai.lastStatus.value, ai.lastError.value, ai.isRunning.value]).toEqual(['cancelled', null, false])
  })
})

describe('describeRunEnd', () => {
  it('names every kind of failure', () => {
    expect(describeRunEnd({
      event: 'end', outcome: 'failed', saved: 0, rejected: 3, save_failures: 2, search_tag_failures: 0, provider_failures: 0
    })).toBe('AI suggestions failed (0 saved): 2 suggestion(s) could not be saved.')
    expect(describeRunEnd({
      event: 'end', outcome: 'complete', saved: 1, rejected: 3, save_failures: 0, search_tag_failures: 0, provider_failures: 0
    })).toBeNull()
  })
})
