// The views of the paired document workspace (#545): text and scan side by side, or one of
// them. A document without scans is shown as text only; a narrow screen has no room for both,
// so there the reader switches between them.

export type WorkspaceMode = 'split' | 'text' | 'scan'

export const WORKSPACE_MODES: readonly WorkspaceMode[] = ['split', 'text', 'scan']

/** The view shown for the chosen one. */
export function shownMode (mode: WorkspaceMode, { hasScan, narrow }: { hasScan: boolean, narrow: boolean }): WorkspaceMode {
  if (!hasScan) return 'text'
  if (mode === 'split' && narrow) return 'text'
  return mode
}

/** A `?view=` value, or null when it names no view. */
export function parseMode (value: unknown): WorkspaceMode | null {
  return typeof value === 'string' && (WORKSPACE_MODES as readonly string[]).includes(value) ? value as WorkspaceMode : null
}

/** `query` with the view chosen (none for the default, text and scan side by side). */
export function withMode<Q extends Record<string, unknown>> (query: Q, mode: WorkspaceMode): Q {
  const next: Record<string, unknown> = { ...query }
  delete next.view
  if (mode !== 'split') next.view = mode
  return next as Q
}
