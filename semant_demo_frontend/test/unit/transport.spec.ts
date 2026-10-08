import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ResponseError } from 'src/generated/api'
import {
  ApiError, BACKEND_URL, apiErrorMessage, clearAuthToken, createApiClients, isAbortError, postNdjson, setAuthToken
} from 'src/shared/api'

const encoder = new TextEncoder()

function streamOf (...lines: string[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start (controller) {
      lines.forEach((line) => controller.enqueue(encoder.encode(line)))
      controller.close()
    }
  })
}

function jsonResponse (body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

type FetchCall = { url: string, headers: Record<string, string> }

describe('shared API transport', () => {
  const originalFetch = globalThis.fetch
  let calls: FetchCall[]
  let respond: (url: string, init?: Parameters<typeof fetch>[1]) => Promise<Response>

  beforeEach(() => {
    calls = []
    respond = () => Promise.resolve(jsonResponse({ status: 'ok' }))
    globalThis.fetch = vi.fn((input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => {
      const headers: Record<string, string> = {}
      new Headers(init?.headers).forEach((value, name) => { headers[name] = value })
      calls.push({ url: String(input), headers })
      return respond(String(input), init)
    }) as typeof fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    clearAuthToken()
  })

  it('authenticates generated-client and NDJSON requests with the current token', async () => {
    const api = createApiClients().default
    setAuthToken('token-1')

    await api.healthHealthGet()
    respond = () => Promise.resolve(new Response(streamOf('{"a":1}\n')))
    await postNdjson('/ai/discuss_span', {}, { onValue: () => undefined })

    // A new token (login as someone else) is used from the next request on.
    setAuthToken('token-2')
    await postNdjson('/ai/discuss_span', {}, { onValue: () => undefined })

    expect(calls.map((c) => c.headers.authorization)).toEqual(['Bearer token-1', 'Bearer token-1', 'Bearer token-2'])
    expect(calls[1].headers.accept).toBe('application/x-ndjson')
    // One backend URL for both kinds of request.
    expect(calls.map((c) => c.url)).toEqual([
      `${BACKEND_URL}/health`, `${BACKEND_URL}/api/ai/discuss_span`, `${BACKEND_URL}/api/ai/discuss_span`
    ])
  })

  it('sends no Authorization header when signed out', async () => {
    await createApiClients().default.healthHealthGet()
    respond = () => Promise.resolve(new Response(streamOf()))
    await postNdjson('/ai/discuss_span', {}, { onValue: () => undefined })

    expect(calls.map((c) => c.headers.authorization)).toEqual([undefined, undefined])
  })

  it('authenticates operations whose schema declares no security', async () => {
    setAuthToken('token-1')
    respond = () => Promise.resolve(jsonResponse({ filters: [] }))

    await createApiClients().default.getAvailableSearchFiltersApiSearchFiltersGet()

    expect(calls[0].headers.authorization).toBe('Bearer token-1')
  })

  it('reports the backend detail of a refused NDJSON request before reading any line', async () => {
    respond = () => Promise.resolve(jsonResponse({ detail: 'Collection not found' }, 404))
    const onValue = vi.fn()

    const error = await postNdjson('/ai/suggest_spans/thorough', {}, { onValue }).catch((e) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect([error.status, error.detail]).toEqual([404, 'Collection not found'])
    expect(await apiErrorMessage(error, 'fallback')).toBe('Collection not found')
    expect(onValue).not.toHaveBeenCalled()
  })

  it('reads the detail of a generated-client error, also for validation errors', async () => {
    respond = () => Promise.resolve(jsonResponse({ detail: [{ msg: 'field required' }, { msg: 'too short' }] }, 422))
    const error = await createApiClients().default.healthHealthGet().catch((e) => e)

    expect(error).toBeInstanceOf(ResponseError)
    expect(await apiErrorMessage(error, 'fallback')).toBe('field required; too short')
    expect(await apiErrorMessage(new Error('network'), 'fallback')).toBe('fallback')
  })

  it('rejects with an abort error when the caller cancels', async () => {
    // Like fetch: rejects at once for an already aborted signal, otherwise on abort.
    respond = (_url, init) => new Promise((_resolve, reject) => {
      const abort = () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' }))
      if (init?.signal?.aborted) abort()
      init?.signal?.addEventListener('abort', abort)
    })
    const controller = new AbortController()

    const streaming = postNdjson('/ai/discuss_span', {}, { onValue: () => undefined, signal: controller.signal })
    controller.abort()
    const ndjsonError = await streaming.catch((e) => e)

    const clientController = new AbortController()
    const request = createApiClients().default.healthHealthGet({ signal: clientController.signal })
    clientController.abort()
    const clientError = await request.catch((e) => e)

    expect([isAbortError(ndjsonError), isAbortError(clientError)]).toEqual([true, true])
    expect(isAbortError(new Error('other'))).toBe(false)
  })
})
