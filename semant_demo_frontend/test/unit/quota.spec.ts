import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { Quasar } from 'quasar'
import { effectScope } from 'vue'

import { ResponseError } from 'src/generated/api'
import {
  ApiError, apiErrorMessage, clearAuthToken, formatQuotaReset, onAiOperation, quotaRefusalMessage, quotaRefusalOf,
  reportAiOperation, setAuthToken
} from 'src/shared/api'
import { useQuotaStore } from 'src/features/quota/quotaStore'
import { useQuotaScope } from 'src/features/quota/useQuotaScope'
import { useUserStore } from 'src/features/auth/userStore'
import QuotaBanner from 'src/features/quota/QuotaBanner.vue'
import QuotaIndicator from 'src/features/quota/QuotaIndicator.vue'
import { generatesText, searchQuotaMessage } from 'src/features/search/searchQuota'

// #234: the daily AI allowance in the frontend.

const NOW = new Date(2026, 9, 17, 12, 0) // local time
const RESET = new Date(2026, 9, 18, 2, 0) // the next UTC midnight, in a UTC+2 zone

type Status = {
  principal: 'guest' | 'account', day?: string, limit_usd?: number, used_usd?: number,
  near_limit?: boolean, exhausted?: boolean, reset_at?: string
}

/** A `QuotaStatusResponse` body; `status` is the JSON body, overriding the defaults. */
function statusBody (status: Status) {
  const body = { day: '2026-10-17', limit_usd: 0.25, used_usd: 0, near_limit: false, exhausted: false, reset_at: RESET.toISOString(), ...status }
  return { ...body, charged_usd: body.used_usd, reserved_usd: 0, remaining_usd: Math.max(0, body.limit_usd - body.used_usd) }
}

function refusalBody (principal: 'guest' | 'account' = 'guest') {
  return {
    detail: 'Insufficient remaining daily AI allowance for this operation; it resets at 2026-10-18 00:00 UTC.',
    code: 'llm_quota_exhausted',
    principal,
    reset_at: RESET.toISOString(),
    limit_usd: 0.25,
    used_usd: 0.25
  }
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

interface Pending { authorization: string | undefined, credentials: RequestCredentials | undefined, answer: (body: unknown, status: number) => void }

describe('daily AI allowance', () => {
  const originalFetch = globalThis.fetch
  let pending: Pending[]

  /** Answers the oldest unanswered `/api/quota` request. */
  async function answer (body: unknown, status = 200) {
    await flushPromises()
    const next = pending.shift()
    if (!next) throw new Error('no quota request is waiting')
    next.answer(body, status)
    await flushPromises()
  }

  beforeEach(() => {
    setActivePinia(createPinia())
    pending = []
    globalThis.fetch = vi.fn((input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => {
      expect(String(input)).toMatch(/\/api\/quota$/)
      const headers = new Headers(init?.headers)
      return new Promise<Response>((resolve) => {
        pending.push({
          authorization: headers.get('authorization') ?? undefined,
          credentials: init?.credentials,
          answer: (body, status) => resolve(json(body, status))
        })
      })
    }) as typeof fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    clearAuthToken()
    vi.useRealTimers()
  })

  describe('refusals', () => {
    it('reads the 429 refusal from both clients and leaves the body readable', async () => {
      const generated = new ResponseError(json(refusalBody(), 429))
      const refusal = await quotaRefusalOf(generated)

      expect(refusal?.principal).toBe('guest')
      expect(refusal?.resetAt).toEqual(RESET)
      expect(await apiErrorMessage(generated, 'x')).toContain('Insufficient remaining daily AI allowance')
      expect((await quotaRefusalOf(new ApiError(429, 'x', refusalBody('account'))))?.principal).toBe('account')
    })

    it('is not a refusal for another 429 or another status', async () => {
      expect(await quotaRefusalOf(new ApiError(429, 'Too many', { detail: 'Too many' }))).toBeNull()
      expect(await quotaRefusalOf(new ApiError(502, 'x', refusalBody()))).toBeNull()
      expect(await quotaRefusalOf(new ResponseError(new Response('busy', { status: 429 })))).toBeNull()
      expect(await quotaRefusalOf(new Error('network'))).toBeNull()
    })

    it('tells when the allowance resets in local time, and guests that logging in gives another one', async () => {
      const refusal = (await quotaRefusalOf(new ApiError(429, 'x', refusalBody())))!
      const time = RESET.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

      expect(formatQuotaReset(RESET, NOW)).toBe(`tomorrow at ${time}`)
      expect(formatQuotaReset(RESET, new Date(2026, 9, 18, 1, 0))).toBe(`today at ${time}`)
      expect(quotaRefusalMessage(refusal, NOW)).toBe(
        'Today\'s AI allowance has no room for this request, so nothing was generated. ' +
        `It resets tomorrow at ${time}; search and browsing still work. Logging in gives you a separate daily allowance.`)
      expect(quotaRefusalMessage({ ...refusal, principal: 'account' }, NOW)).not.toContain('Logging in')
    })

    it('explains skipped Search titles and summaries without calling it a failure', async () => {
      const refusal = (await quotaRefusalOf(new ApiError(429, 'x', refusalBody())))!

      expect(searchQuotaMessage(refusal, NOW)).toMatch(/^AI titles and summaries were skipped: today's AI allowance/)
      expect(searchQuotaMessage(refusal, NOW)).toContain('The search results are complete')
      expect(generatesText({ query: 'q', tagUuids: [], positive: true, automatic: true })).toBe(false)
      expect(generatesText({ query: 'q', tagUuids: [], positive: true, automatic: true, searchTitleGenerate: true })).toBe(true)
    })
  })

  describe('store', () => {
    it('reads the allowance with the browser\'s cookies and shows the share used', async () => {
      const quota = useQuotaStore()
      void quota.follow('guest')
      await flushPromises()
      expect(pending[0].credentials).toBe('include')
      await answer(statusBody({ principal: 'guest', used_usd: 0.05 }))

      expect(quota.usedPercent).toBe(20)
      expect(quota.level).toBe('ok')
    })

    it('reaches the near-limit and exhausted levels from the backend\'s flags', async () => {
      const quota = useQuotaStore()
      void quota.follow('guest')
      await answer(statusBody({ principal: 'guest', used_usd: 0.2, near_limit: true }))
      expect([quota.usedPercent, quota.level]).toEqual([80, 'near'])

      void quota.refresh()
      await answer(statusBody({ principal: 'guest', used_usd: 0.31, near_limit: true, exhausted: true }))
      // An admitted operation may finish past the allowance; more than all is shown as all.
      expect([quota.usedPercent, quota.level]).toEqual([100, 'exhausted'])
    })

    it('never shows an earlier principal\'s allowance after a switch', async () => {
      const quota = useQuotaStore()
      void quota.follow('account')
      await flushPromises()
      void quota.follow('guest') // signed out before the account's answer arrived
      await answer(statusBody({ principal: 'account', limit_usd: 1, used_usd: 0.9, near_limit: true }))

      expect(quota.status).toBeNull()
      await answer(statusBody({ principal: 'guest' }))
      expect(quota.status?.principal).toBe('guest')
    })

    it('does not show an answer for another kind of principal than the followed one', async () => {
      const quota = useQuotaStore()
      void quota.follow('account')
      await answer(statusBody({ principal: 'guest' })) // e.g. the token expired meanwhile

      expect(quota.status).toBeNull()
    })

    it('reads once more after a refresh asked for during one, not once per request', async () => {
      const quota = useQuotaStore()
      void quota.follow('guest')
      void quota.refresh()
      void quota.refresh()
      await answer(statusBody({ principal: 'guest', used_usd: 0.01 }))
      await answer(statusBody({ principal: 'guest', used_usd: 0.1 }))

      expect(pending).toEqual([])
      expect(quota.usedPercent).toBe(40)
    })

    it('keeps the last allowance when a refresh fails', async () => {
      const quota = useQuotaStore()
      void quota.follow('guest')
      await answer(statusBody({ principal: 'guest', used_usd: 0.05 }))
      void quota.refresh()
      await answer({ detail: 'Internal Server Error' }, 500)

      expect(quota.failed).toBe(true)
      expect(quota.usedPercent).toBe(20)
    })

    it('reads the new day\'s allowance once, when the UTC day rolls over', async () => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date('2026-10-17T23:59:00Z'))
      const quota = useQuotaStore()
      void quota.follow('guest')
      await answer(statusBody({ principal: 'guest', used_usd: 0.25, near_limit: true, exhausted: true, reset_at: '2026-10-18T00:00:00Z' }))
      expect(quota.level).toBe('exhausted')

      vi.advanceTimersByTime(59_000)
      await flushPromises()
      expect(pending).toEqual([]) // not polled
      vi.advanceTimersByTime(2_000)
      await answer(statusBody({ principal: 'guest', day: '2026-10-18', reset_at: '2026-10-19T00:00:00Z' }))

      expect([quota.status?.day, quota.level]).toEqual(['2026-10-18', 'ok'])
    })
  })

  describe('scope', () => {
    function startScope () {
      const scope = effectScope()
      scope.run(() => useQuotaScope())
      return scope
    }

    it('follows the guest, then the verified account, and forgets the account on sign-out', async () => {
      const userStore = useUserStore()
      const quota = useQuotaStore()
      const scope = startScope()
      await answer(statusBody({ principal: 'guest', used_usd: 0.05 }))
      expect(quota.status?.principal).toBe('guest')

      setAuthToken('token-a')
      userStore.token = 'token-a'
      await flushPromises()
      // Awaiting verification: neither the guest's nor any account's allowance.
      expect(quota.status).toBeNull()
      expect(pending).toEqual([])

      userStore.user = { id: 'uA', email: 'a@example.com', username: 'a', name: 'A' } as never
      await flushPromises()
      expect(pending[0].authorization).toBe('Bearer token-a')
      await answer(statusBody({ principal: 'account', limit_usd: 1, used_usd: 0.5 }))
      expect(quota.status?.principal).toBe('account')

      userStore.forgetSession()
      await flushPromises()
      expect(quota.status).toBeNull()
      expect(pending[0].authorization).toBeUndefined()
      await answer(statusBody({ principal: 'guest', used_usd: 0.05 }))
      expect(quota.status?.principal).toBe('guest')
      scope.stop()
    })

    it('reads the allowance again after each AI operation', async () => {
      const quota = useQuotaStore()
      const scope = startScope()
      await answer(statusBody({ principal: 'guest' }))

      reportAiOperation()
      await answer(statusBody({ principal: 'guest', used_usd: 0.1 }))
      expect(quota.usedPercent).toBe(40)

      scope.stop()
      reportAiOperation()
      await flushPromises()
      expect(pending).toEqual([])
    })

    it('unsubscribes listeners', () => {
      const listener = vi.fn()
      const stop = onAiOperation(listener)
      reportAiOperation()
      stop()
      reportAiOperation()
      expect(listener).toHaveBeenCalledTimes(1)
    })
  })

  describe('display', () => {
    async function showStatus (status: Status) {
      const quota = useQuotaStore()
      void quota.follow(status.principal)
      await answer(statusBody(status))
    }

    const mountWithQuasar = <T>(component: T) => mount(component as never, { global: { plugins: [Quasar] } })

    it('shows no banner below the near-limit share', async () => {
      await showStatus({ principal: 'guest', used_usd: 0.1 })
      expect(mountWithQuasar(QuotaBanner).find('[data-testid="quota-banner"]').exists()).toBe(false)
    })

    it('warns a guest near the limit and offers Log in and Register', async () => {
      await showStatus({ principal: 'guest', used_usd: 0.2, near_limit: true })
      const banner = mountWithQuasar(QuotaBanner)

      expect(banner.text()).toContain('You have used 80% of today\'s AI allowance. It resets')
      const buttons = banner.findAll('button').map((b) => b.text())
      expect(buttons).toEqual(['Log in', 'Register', 'Dismiss'])
      await banner.findAll('button')[0].trigger('click')
      expect(banner.emitted('login')).toHaveLength(1)
    })

    it('tells an account user the allowance is used up without asking them to register', async () => {
      await showStatus({ principal: 'account', limit_usd: 1, used_usd: 1, near_limit: true, exhausted: true })
      const banner = mountWithQuasar(QuotaBanner)

      expect(banner.text()).toContain('Today\'s AI allowance is used up.')
      expect(banner.text()).toContain('search and browsing still work')
      expect(banner.findAll('button').map((b) => b.text())).toEqual(['Dismiss'])
    })

    it('stays dismissed for the same level and returns at the next one', async () => {
      await showStatus({ principal: 'guest', used_usd: 0.2, near_limit: true })
      const banner = mountWithQuasar(QuotaBanner)
      await banner.findAll('button').at(-1)!.trigger('click')
      expect(banner.find('[data-testid="quota-banner"]').exists()).toBe(false)

      void useQuotaStore().refresh()
      await answer(statusBody({ principal: 'guest', used_usd: 0.21, near_limit: true }))
      expect(banner.find('[data-testid="quota-banner"]').exists()).toBe(false)

      void useQuotaStore().refresh()
      await answer(statusBody({ principal: 'guest', used_usd: 0.25, near_limit: true, exhausted: true }))
      expect(banner.text()).toContain('used up')
    })

    it('shows a warning dismissed by one account again to another account at the same level', async () => {
      const userStore = useUserStore()
      const scope = effectScope()
      scope.run(() => useQuotaScope())
      await answer(statusBody({ principal: 'guest' }))
      setAuthToken('token-a')
      userStore.token = 'token-a'
      userStore.user = { id: 'uA', email: 'a@example.com', username: 'a', name: 'A' } as never
      await answer(statusBody({ principal: 'account', limit_usd: 1, used_usd: 0.9, near_limit: true }))
      const banner = mountWithQuasar(QuotaBanner)
      await banner.findAll('button').at(-1)!.trigger('click')
      expect(banner.find('[data-testid="quota-banner"]').exists()).toBe(false)

      // Another account, the same day and level: its own warning is not dismissed.
      setAuthToken('token-b')
      userStore.token = 'token-b'
      userStore.user = { id: 'uB', email: 'b@example.com', username: 'b', name: 'B' } as never
      await answer(statusBody({ principal: 'account', limit_usd: 1, used_usd: 0.85, near_limit: true }))
      expect(banner.text()).toContain('You have used 85% of today\'s AI allowance.')
      scope.stop()
    })

    it('shows the share left in the header', async () => {
      await showStatus({ principal: 'guest', used_usd: 0.05 })
      const indicator = mountWithQuasar(QuotaIndicator)

      expect(indicator.find('button').attributes('aria-label')).toBe('AI allowance: 80% left today')
    })

    it('shows nothing before the allowance is known', () => {
      expect(mountWithQuasar(QuotaIndicator).find('button').exists()).toBe(false)
    })
  })
})
