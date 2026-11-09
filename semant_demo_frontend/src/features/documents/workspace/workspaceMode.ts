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

/**
 * `query` after the reader moved to page `pageId` in the scan viewer: the page is kept
 * (`?page=`) and the link targets it replaces (`targets`, e.g. a passage) are dropped, so a
 * reload opens the page the reader moved to. Only the reader's own page changes are kept: the
 * first page and pages opened for the text leave the link as it was.
 */
export function withScanPage<Q extends Record<string, unknown>> (query: Q, pageId: string, targets: readonly string[]): Q {
  const next: Record<string, unknown> = { ...query }
  for (const key of targets) delete next[key]
  next.page = pageId
  return next as Q
}

/** A key of the link targets `keys` in `query`: a change of the target, not of other parameters. */
export function targetKey (query: Record<string, unknown>, keys: readonly string[]): string {
  return JSON.stringify(keys.map(k => query[k] ?? null))
}
