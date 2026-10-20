import { afterEach, vi, type SpyInstance } from 'vitest'

// For a test that provokes a failure the code logs on purpose: the expected message is
// checked instead of printed, so the output of a passing run shows only real problems.

const muted: SpyInstance[] = []

afterEach(() => {
  for (const spy of muted.splice(0)) spy.mockRestore()
})

/** Silences `console[method]` until the end of the test; returns the spy to assert on. */
export function muteConsole (method: 'error' | 'warn'): SpyInstance {
  const spy = vi.spyOn(console, method).mockImplementation(() => undefined)
  muted.push(spy)
  return spy
}
