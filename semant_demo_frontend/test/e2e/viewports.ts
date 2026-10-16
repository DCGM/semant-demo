/**
 * The three layouts reviewed for UI work (CONTRIBUTING.md, UI change checklist), shared by
 * browser specs (`useViewport` in support.ts) and the capture projects in playwright.config.ts.
 */
export const viewports = {
  wide: { width: 1920, height: 1000 },
  /** Constrained desktop: wide enough that both sidebars open beside the main column. */
  narrow: { width: 1280, height: 900 },
  /** Below Quasar's drawer breakpoint: both sidebars become overlays. */
  phone: { width: 390, height: 844 }
} as const

export type ViewportName = keyof typeof viewports
