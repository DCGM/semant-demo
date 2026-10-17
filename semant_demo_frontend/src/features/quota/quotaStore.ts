import { defineStore } from 'pinia'
import type { QuotaStatusResponse } from 'src/generated/api'
import { createContextGuard, useApi } from 'src/shared/api'

/** Whose allowance the page shows: a guest's, a verified account's, or nobody's (a stored session awaiting verification). */
export type QuotaPrincipal = 'guest' | 'account' | null

export type QuotaLevel = 'ok' | 'near' | 'exhausted'

// Answers to requests made for an earlier principal (sign-in, sign-out, account switch) are dropped.
const principalContext = createContextGuard()
let inFlight: Promise<void> | null = null
let refreshAgain = false
let rollover: ReturnType<typeof setTimeout> | null = null

function stopRollover () {
  if (rollover !== null) clearTimeout(rollover)
  rollover = null
}

interface QuotaStoreState {
  principal: QuotaPrincipal
  status: QuotaStatusResponse | null
  /** The last refresh failed; `status`, if any, is the last one read. */
  failed: boolean
}

/**
 * The current principal's daily AI allowance (`GET /api/quota`, #371). Read when the
 * principal changes, after each AI operation (`reportAiOperation`) and once when the
 * UTC day rolls over; never polled. Only the allowance of the principal followed now is
 * kept: following another one forgets the shown allowance at once.
 */
export const useQuotaStore = defineStore('quota', {
  state: (): QuotaStoreState => ({ principal: null, status: null, failed: false }),

  getters: {
    /** Share of the day's allowance used, 0–100 (more is shown as 100). */
    usedPercent: (state): number | null => {
      const status = state.status
      if (!status) return null
      if (status.limitUsd <= 0) return 100
      return Math.min(100, Math.max(0, Math.round(status.usedUsd / status.limitUsd * 100)))
    },
    level: (state): QuotaLevel | null => {
      const status = state.status
      if (!status) return null
      if (status.exhausted) return 'exhausted'
      return status.nearLimit ? 'near' : 'ok'
    }
  },

  actions: {
    /**
     * Shows `principal`'s allowance from now on: forgets the current one (also when it is
     * the same kind, e.g. another account) and reads the new one, unless nobody is followed.
     */
    follow (principal: QuotaPrincipal): Promise<void> {
      principalContext.enter()
      stopRollover()
      inFlight = null
      refreshAgain = false
      this.principal = principal
      this.status = null
      this.failed = false
      return principal ? this.refresh() : Promise.resolve()
    },

    /**
     * Reads the allowance again. A refresh asked for while one is under way runs once more
     * after it, so the last read follows the last AI operation.
     */
    refresh (): Promise<void> {
      const principal = this.principal
      if (!principal) return Promise.resolve()
      if (inFlight) {
        refreshAgain = true
        return inFlight
      }
      const isCurrent = principalContext.capture()
      const run = async () => {
        do {
          refreshAgain = false
          try {
            const status = await useApi().default.getQuotaStatusApiQuotaGet()
            if (!isCurrent()) return
            // Not the followed principal (e.g. a token that expired meanwhile): not shown.
            if (status.principal !== principal) continue
            this.status = status
            this.failed = false
            this.scheduleRollover(status.resetAt)
          } catch {
            if (!isCurrent()) return
            this.failed = true
          }
        } while (refreshAgain && isCurrent())
      }
      const promise = run().finally(() => { if (inFlight === promise) inFlight = null })
      inFlight = promise
      return promise
    },

    /** Reads the new day's allowance once the current one resets (a single timer, not polling). */
    scheduleRollover (resetAt: Date) {
      stopRollover()
      const delay = Math.max(1000, resetAt.getTime() - Date.now() + 1000)
      rollover = setTimeout(() => {
        rollover = null
        void this.refresh()
      }, delay)
    }
  }
})
