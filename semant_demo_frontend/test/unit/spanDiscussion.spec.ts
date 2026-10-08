import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import useSpanDiscussion from 'src/composables/useSpanDiscussion'

const encoder = new TextEncoder()
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

/** A reply stream that keeps delivering after abort (a read already under way). */
function replyStream () {
  let controller!: { enqueue (chunk: Uint8Array): void, close (): void }
  const body = new ReadableStream<Uint8Array>({ start (c) { controller = c } })
  return {
    body,
    delta: (text: string) => controller.enqueue(encoder.encode(JSON.stringify({ delta: text }) + '\n')),
    close: () => controller.close()
  }
}

describe('useSpanDiscussion', () => {
  const originalFetch = globalThis.fetch
  let streams: ReturnType<typeof replyStream>[]
  let bodies: unknown[]

  beforeEach(() => {
    streams = []
    bodies = []
    globalThis.fetch = vi.fn((_url: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => {
      const stream = replyStream()
      streams.push(stream)
      bodies.push(JSON.parse(String(init?.body)))
      return Promise.resolve(new Response(stream.body))
    }) as typeof fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('streams the reply and sends the history without the placeholder', async () => {
    const chat = useSpanDiscussion()
    chat.reset({ spanId: 's1' })
    const sending = chat.send('Why?')
    await flush()
    streams[0].delta('Be')
    streams[0].delta('cause.')
    streams[0].close()
    await sending

    expect(bodies[0]).toEqual({ span_id: 's1', messages: [{ role: 'user', content: 'Why?' }] })
    expect(chat.messages.value).toEqual([{ role: 'user', content: 'Why?' }, { role: 'assistant', content: 'Because.' }])
    expect(chat.isStreaming.value).toBe(false)
  })

  it('keeps a late reply of the previous span out of the new conversation', async () => {
    const chat = useSpanDiscussion()
    chat.reset({ spanId: 's1' })
    const old = chat.send('About s1')
    await flush()

    chat.reset({ spanId: 's2' }) // dialog reopened for another span
    const current = chat.send('About s2')
    await flush()
    streams[0].delta('late answer about s1')
    streams[0].close()
    await old

    expect(chat.messages.value).toEqual([{ role: 'user', content: 'About s2' }, { role: 'assistant', content: '' }])
    expect(chat.isStreaming.value).toBe(true) // the old reply's end does not end the new one

    streams[1].delta('answer about s2')
    streams[1].close()
    await current
    expect(chat.messages.value.map((m) => m.content)).toEqual(['About s2', 'answer about s2'])
  })

  it('drops deltas after cancel and keeps what arrived before', async () => {
    const chat = useSpanDiscussion()
    chat.reset({ spanId: 's1' })
    const sending = chat.send('Q1')
    await flush()
    streams[0].delta('partial')
    await flush()

    chat.cancel()
    const next = chat.send('Q2')
    await flush()
    streams[0].delta(' late')
    streams[0].close()
    await sending

    expect(chat.messages.value.map((m) => m.content)).toEqual(['Q1', 'partial', 'Q2', ''])
    expect(chat.isStreaming.value).toBe(true)
    streams[1].close()
    await next
    // An empty reply is removed; only the turn's own placeholder.
    expect(chat.messages.value.map((m) => m.content)).toEqual(['Q1', 'partial', 'Q2'])
  })
})
