import { describe, expect, it } from 'vitest'
import { matchesAiRun } from 'src/features/annotations/aiRunHistory'

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
