import { describe, expect, it } from 'vitest'
import {
  matchesAiRun, runOutcomeDescription, runOutcomeLabel, type AiSuggestionRunInfo
} from 'src/features/annotations/aiRunHistory'

describe('AI run filter (#801)', () => {
  const known = new Set(['run-a', 'run-b'])

  it('shows every proposal under All runs', () => {
    expect(matchesAiRun('run-a', null, known)).toBe(true)
    expect(matchesAiRun(null, null, known)).toBe(true)
  })

  it('shows only proposals of the selected run', () => {
    expect(matchesAiRun('run-a', 'run-a', known)).toBe(true)
    expect(matchesAiRun('run-b', 'run-a', known)).toBe(false)
    expect(matchesAiRun(null, 'run-a', known)).toBe(false)
  })

  it('keeps pre-history or unknown-run proposals accessible', () => {
    expect(matchesAiRun(null, 'legacy', known)).toBe(true)
    expect(matchesAiRun('old-untracked-run', 'legacy', known)).toBe(true)
    expect(matchesAiRun('run-a', 'legacy', known)).toBe(false)
  })
})

describe('AI run outcome explanations', () => {
  const run: AiSuggestionRunInfo = {
    id: 'run-a', mode: 'optimized', config_name: 'fake-local', tag_ids: ['tag'],
    started_at: '2026-11-24T10:00:00Z', finished_at: '2026-11-24T10:01:00Z',
    outcome: 'cancelled', saved: 2, unit: 'call', units_total: 5, units_completed: 2,
    provider_failures: 0, save_failures: 0
  }

  it('reports completed operations and retained suggestions on cancellation', () => {
    expect(runOutcomeLabel(run)).toBe('Cancelled · 2/5 calls')
    expect(runOutcomeDescription(run)).toContain('2/5 calls completed')
    expect(runOutcomeDescription(run)).toContain('2 suggestion(s) saved')
  })

  it('explains failed AI operations rather than just showing Failed', () => {
    const failed = { ...run, outcome: 'failed', saved: 0, provider_failures: 3, units_completed: 3 }
    expect(runOutcomeLabel(failed)).toBe('Failed · 3/5 calls')
    expect(runOutcomeDescription(failed)).toContain('no AI call completed successfully')
    expect(runOutcomeDescription(failed)).toContain('3 AI operation(s) failed')
  })

  it('does not invent a total for a run interrupted before work started', () => {
    const interrupted = { ...run, outcome: 'cancelled', units_total: 0, units_completed: 0 }
    expect(runOutcomeLabel(interrupted)).toBe('Cancelled')
    expect(runOutcomeDescription(interrupted)).not.toContain('0/0')
  })
})
