import { describe, expect, it } from 'vitest'
import { navigationScrollBehavior } from 'src/features/documents/viewer/textReveal'

describe('AI suggestion navigation scroll', () => {
  const viewport = { top: 0, bottom: 600 }

  it('keeps a smooth scroll for suggestions near the current text', () => {
    expect(navigationScrollBehavior({ top: 650, bottom: 670 }, viewport)).toBe('smooth')
    expect(navigationScrollBehavior({ top: 100, bottom: 120 }, viewport)).toBe('smooth')
  })

  it('jumps immediately instead of animating across distant pages', () => {
    expect(navigationScrollBehavior({ top: 2200, bottom: 2220 }, viewport)).toBe('instant')
    expect(navigationScrollBehavior({ top: -2500, bottom: -2480 }, viewport)).toBe('instant')
  })

  it('keeps smooth behavior when the viewport cannot be measured', () => {
    expect(navigationScrollBehavior({ top: 2000, bottom: 2010 }, { top: 0, bottom: 0 })).toBe('smooth')
  })
})
