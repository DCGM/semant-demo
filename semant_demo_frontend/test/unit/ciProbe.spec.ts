import { expect, it } from 'vitest'

// TEMPORARY: deliberate failure to prove CI blocks (#199). Reverted in the next commit.
it('deliberately fails', () => {
  expect(1).toBe(2)
})
