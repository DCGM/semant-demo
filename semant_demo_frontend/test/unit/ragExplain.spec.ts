import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Notify, QLayout, QPageContainer, Quasar } from 'quasar'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'

import { onAiOperation } from 'src/shared/api'
import RagPage from 'src/features/rag/RagPage.vue'

// #234 review: Explain in the Chat Assistant is an AI operation like an answer. A refusal for
// the daily allowance says why and when it resets, and every Explain reads the allowance again.

const source = { id: 'ch1', text: 'Source text', document: 'd1', document_object: { id: 'd1' } }

let answers: Record<string, () => Response>
let sent: string[]
const originalFetch = globalThis.fetch

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

beforeEach(() => {
  setActivePinia(createPinia())
  vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined) // the dialog restores the scroll; jsdom has none
  sent = []
  answers = {
    '/api/rag/configurations': () => json([{ id: 'r1', name: 'RAG', description: '' }]),
    '/api/rag': () => json({ rag_answer: 'Answer that can be explained [doc 1]', sources: [source], response_id: 'x', time_spent: 1 })
  }
  globalThis.fetch = vi.fn((input: Parameters<typeof fetch>[0]) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const path = new URL(url, 'http://localhost').pathname
    sent.push(path)
    const answer = answers[path]
    return answer ? Promise.resolve(answer()) : new Promise<Response>(() => undefined)
  }) as typeof fetch
})

afterEach(() => {
  globalThis.fetch = originalFetch
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

/** Asks a question, selects the answer and clicks Explain; returns the AI operations reported. */
async function explainAnswer () {
  const InLayout = defineComponent({ render: () => h(QLayout, () => [h(QPageContainer, () => h(RagPage))]) })
  const layout = mount(InLayout, { attachTo: document.body, global: { plugins: [[Quasar, { plugins: { Notify } }]] } })
  await flushPromises()
  const wrapper = layout.findComponent(RagPage)
  await wrapper.find('input[placeholder="Vaše otázka?"]').setValue('Question')
  await wrapper.findAll('button').find((b) => b.text() === 'send')!.trigger('click')
  await flushPromises()

  const operations = vi.fn()
  const stop = onAiOperation(operations)
  const answerText = wrapper.findAll('.markdown-body').at(-1)!
  const range = document.createRange()
  range.selectNodeContents(answerText.element)
  range.getClientRects = () => [{ right: 10, bottom: 10 }] as unknown as DOMRectList // jsdom has no layout
  window.getSelection()!.removeAllRanges()
  window.getSelection()!.addRange(range)
  await answerText.trigger('mouseup')
  await wrapper.findAll('button').find((b) => b.text() === 'Explain')!.trigger('click')
  await flushPromises()
  stop()
  return { operations, unmount: () => layout.unmount() }
}

describe('Explain and the daily AI allowance', () => {
  it('says why a refused explanation was not generated, asks once and reads the allowance again', async () => {
    answers['/api/rag/explain'] = () => json({
      detail: 'Insufficient remaining daily AI allowance for this operation; it resets at 2026-10-18 00:00 UTC.',
      code: 'llm_quota_exhausted',
      principal: 'guest',
      reset_at: new Date(Date.now() + 3600_000).toISOString(),
      limit_usd: 0.25,
      used_usd: 0.25
    }, 429)

    const { operations, unmount } = await explainAnswer()

    expect(document.body.textContent).toContain('Today\'s AI allowance has no room for this request, so nothing was generated.')
    expect(document.body.textContent).not.toContain('Sorry, this part can not be explained.')
    expect(sent.filter((path) => path === '/api/rag/explain')).toHaveLength(1)
    expect(operations).toHaveBeenCalledTimes(1)
    unmount()
  })

  it('keeps the generic message for other failures', async () => {
    answers['/api/rag/explain'] = () => json({ detail: 'boom' }, 500)

    const { operations, unmount } = await explainAnswer()

    expect(document.body.textContent).toContain('Sorry, this part can not be explained.')
    expect(operations).toHaveBeenCalledTimes(1)
    unmount()
  })

  it('reads the allowance again after a successful explanation', async () => {
    answers['/api/rag/explain'] = () => json({ explanation: 'Because of [doc 1]' })

    const { operations, unmount } = await explainAnswer()

    expect(document.body.textContent).toContain('Because of')
    expect(operations).toHaveBeenCalledTimes(1)
    unmount()
  })
})
