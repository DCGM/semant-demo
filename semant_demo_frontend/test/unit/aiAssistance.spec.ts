import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { onAiOperation, readNdjson } from 'src/shared/api'
import useAiAssistance, {
  describeRunEnd, describeTagLimits, largeRunWarning
} from 'src/features/annotations/useAiAssistance'
import { useTagSpansStore } from 'src/features/annotations/tagSpansStore'
import { useTopicerModelStore } from 'src/features/annotations/topicerModelStore'
import { muteConsole } from './console'

vi.mock('src/features/annotations/useTagSpansRepository', () => ({ useTagSpansRepository: () => ({}) }))

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

  it('names the chosen model in document and selection requests only when one is chosen', async () => {
    const ai = useAiAssistance()
    const bodies = () => vi.mocked(globalThis.fetch).mock.calls.map(([, init]) => JSON.parse(String(init?.body)))
    for (const configName of [undefined, null, 'crossbert']) {
      const running = ai.run({ ...request('d1'), configName })
      await flush()
      streams[streams.length - 1].close()
      await running
    }
    const selection = ai.runOnSelection({
      collectionId: 'c', documentId: 'd1', chunkIds: ['x'], selectionStart: 0, selectionEnd: 3, tagIds: ['t'], configName: 'crossbert'
    })
    await flush()
    streams[streams.length - 1].close()
    await selection

    expect(bodies().map((b) => b.config_name)).toEqual([undefined, undefined, 'crossbert', 'crossbert'])
  })

  it('reads the model list again when the backend refuses a request that named a model', async () => {
    muteConsole('error')
    const reload = vi.spyOn(useTopicerModelStore(), 'reload').mockResolvedValue()
    const refused = () => Promise.resolve(new Response(JSON.stringify({ detail: 'Unknown AI model' }), { status: 400 }))
    vi.mocked(globalThis.fetch).mockImplementation(refused)
    const ai = useAiAssistance()

    await ai.run({ ...request('d1'), configName: 'gone' })
    await ai.run(request('d1'))
    await ai.runOnSelection({
      collectionId: 'c', documentId: 'd1', chunkIds: ['x'], selectionStart: 0, selectionEnd: 3, tagIds: ['t'], configName: 'gone'
    })

    expect(ai.lastError.value).toBe('Unknown AI model')
    expect(reload).toHaveBeenCalledTimes(2)
  })

  it('reports a cancelled run without an error', async () => {
    const ai = useAiAssistance()
    const running = ai.run(request('d1'))
    await flush()

    ai.cancel()
    await running

    expect([ai.lastStatus.value, ai.lastError.value, ai.isRunning.value]).toEqual(['cancelled', null, false])
  })

  it('refreshes the allowance after every run, also a cancelled or refused one', async () => {
    const reported = vi.fn()
    const unsubscribe = onAiOperation(reported)
    const ai = useAiAssistance()

    const completed = ai.run(request('d1'))
    await flush()
    streams[0].push(end('complete'))
    streams[0].close()
    await completed
    const cancelled = ai.run(request('d1'))
    await flush()
    ai.cancel()
    await cancelled
    const selection = ai.runOnSelection({
      collectionId: 'c', documentId: 'd1', chunkIds: ['x'], selectionStart: 0, selectionEnd: 3, tagIds: ['t']
    })
    await flush()
    streams[2].push(end('complete'))
    streams[2].close()
    await selection
    unsubscribe()

    expect(reported).toHaveBeenCalledTimes(3)
  })

  it('shows a refusal for the daily allowance with its reset time and does not retry', async () => {
    const logged = muteConsole('error')
    const resetAt = new Date(Date.now() + 3_600_000).toISOString()
    const refusal = {
      detail: 'Insufficient remaining daily AI allowance',
      code: 'llm_quota_exhausted',
      principal: 'account',
      reset_at: resetAt,
      limit_usd: 1,
      used_usd: 1
    }
    globalThis.fetch = vi.fn(() => Promise.resolve(new Response(JSON.stringify(refusal), { status: 429 })))
    const ai = useAiAssistance()

    await ai.run(request('d1'))

    expect(ai.lastError.value).toMatch(/^Today's AI allowance has no room for this request, so nothing was generated. It resets/)
    expect(globalThis.fetch).toHaveBeenCalledTimes(1)
    expect(logged).toHaveBeenCalledWith('AI assistance failed', expect.anything())
  })

  it('reports an early stop for the allowance and the tags that reached the chunk limit', async () => {
    const ai = useAiAssistance()
    const running = ai.run({ ...request('d1'), mode: 'optimized' })
    await flush()

    streams[0].push(end('partial', {
      saved: 3,
      unit: 'tag',
      units_total: 3,
      units_processed: 2,
      stop_reason: 'quota_exhausted',
      quota_exhausted: { reset_at: new Date(Date.now() + 3_600_000).toISOString(), principal: 'account' },
      max_chunks_per_tag: 40,
      tag_limits: [{ tag_id: 't', tag_name: 'Person', max_chunks: 40, processed_chunks: 40, candidates_truncated: true }]
    }))
    streams[0].close()
    await running

    expect(ai.lastError.value).toMatch(
      /^Today's remaining AI allowance is not enough for the next AI operation, so AI suggestions stopped early: 2 of 3 tags processed, 3 suggestion\(s\) saved. It resets /)
    expect(ai.lastNotices.value).toEqual(['Tag "Person" reached the limit of 40 chunks per tag; additional candidate chunks were excluded.'])
    ai.reset()
    expect(ai.lastNotices.value).toEqual([])
  })
})

describe('largeRunWarning', () => {
  it('asks above 50 thorough chunks only', () => {
    expect(largeRunWarning('thorough', 50, 3, 40)).toBeNull()
    expect(largeRunWarning('thorough', 51, 1, 40)).toMatch(/all 51 chunks/)
  })

  it('asks when the optimized maximum, tags times the backend limit, exceeds 50', () => {
    expect(largeRunWarning('optimized', 500, 1, 40)).toBeNull()
    expect(largeRunWarning('optimized', 500, 5, 10)).toBeNull() // exactly 50
    expect(largeRunWarning('optimized', 1, 2, 40)).toMatch(/up to 80 chunks \(2 tag\(s\) × at most 40 chunks per tag\)/)
    expect(largeRunWarning('optimized', 1, 2, 20)).toBeNull()
    expect(largeRunWarning('optimized', 1, 3, 20)).toMatch(/up to 60 chunks/)
  })
})

describe('describeTagLimits', () => {
  it('says that candidates were excluded only when they were', () => {
    const limit = { tag_id: 't', tag_name: 'Place', max_chunks: 20, processed_chunks: 20 }
    expect(describeTagLimits({
      ...JSON.parse(end('complete')),
      tag_limits: [{ ...limit, candidates_truncated: false }, { ...limit, tag_name: 'Person', candidates_truncated: true }]
    })).toEqual([
      'Tag "Place" reached the limit of 20 chunks per tag.',
      'Tag "Person" reached the limit of 20 chunks per tag; additional candidate chunks were excluded.'
    ])
    expect(describeTagLimits(null)).toEqual([])
  })
})

describe('describeRunEnd', () => {
  it('names every kind of failure', () => {
    expect(describeRunEnd({
      event: 'end', outcome: 'failed', saved: 0, rejected: 3, save_failures: 2, search_tag_failures: 0, provider_failures: 0
    })).toBe('AI suggestions failed (0 saved): 2 suggestion(s) could not be saved.')
    expect(describeRunEnd({
      event: 'end', outcome: 'partial', saved: 2, rejected: 0, save_failures: 0, search_tag_failures: 0, enrichment_failures: 1, provider_failures: 0
    })).toBe('AI suggestions were only partly completed (2 saved): 1 saved suggestion(s) without current search text or similarity vector.')
    expect(describeRunEnd({
      event: 'end', outcome: 'complete', saved: 1, rejected: 3, save_failures: 0, search_tag_failures: 0, provider_failures: 0
    })).toBeNull()
  })
})
