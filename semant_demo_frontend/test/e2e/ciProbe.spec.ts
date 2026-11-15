import { expect, test } from '@playwright/test'

// CI probe for #687 stage 2: deliberately failing (throwaway, not to be merged).
test('CI probe fails on purpose', () => {
  expect(1).toBe(2)
})
