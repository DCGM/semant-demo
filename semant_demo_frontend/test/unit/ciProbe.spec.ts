import { describe, expect, it } from 'vitest'

// CI probe for #687 stage 2: deliberately failing (throwaway, not to be merged).
describe('CI probe', () => {
  it('fails on purpose', () => {
    expect(1).toBe(2)
  })
})
