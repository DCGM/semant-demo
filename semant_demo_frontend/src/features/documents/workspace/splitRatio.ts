// The split between the text and the scan of the document workspace (#600): the text's
// share of the width both panes have, remembered in this browser.
import { readStored, writeStored } from 'src/shared/browserStorage'

export const SPLIT_STORAGE_KEY = 'semant.documentWorkspace.textShare'
/** The text's share when nothing (valid) is remembered. */
export const DEFAULT_TEXT_SHARE = 0.55
/** The narrowest usable panes, in px; the workspace falls back to one pane below both (NARROW_WIDTH). */
export const MIN_TEXT_WIDTH = 360
export const MIN_SCAN_WIDTH = 300
/** The width of the divider between the panes, in px. */
export const DIVIDER_WIDTH = 8
/** One arrow-key step of the divider, and one with Shift. */
export const KEY_STEP = 0.02
export const LARGE_KEY_STEP = 0.1

/** The shares the text can have in a workspace `width` px wide: both panes keep their minimum. */
export function shareBounds (width: number): { min: number, max: number } {
  const room = width - DIVIDER_WIDTH
  if (room <= MIN_TEXT_WIDTH + MIN_SCAN_WIDTH) return { min: 0.5, max: 0.5 }
  return { min: MIN_TEXT_WIDTH / room, max: 1 - MIN_SCAN_WIDTH / room }
}

/** `share` within the bounds of a workspace `width` px wide (unbounded while it is unknown). */
export function clampShare (share: number, width: number): number {
  if (!(width > 0)) return Math.min(1, Math.max(0, share))
  const { min, max } = shareBounds(width)
  return Math.min(max, Math.max(min, share))
}

/** The text's share with the divider at `x` px from the workspace's left edge (the text is right of it). */
export function shareAt (x: number, width: number): number {
  return clampShare((width - x - DIVIDER_WIDTH / 2) / (width - DIVIDER_WIDTH), width)
}

/** The remembered share, if it is a share. */
export function readShare (): number {
  const stored = readStored(SPLIT_STORAGE_KEY)
  const value = stored === null ? NaN : Number(stored)
  return value > 0 && value < 1 ? value : DEFAULT_TEXT_SHARE
}

export function storeShare (share: number): void {
  writeStored(SPLIT_STORAGE_KEY, share.toFixed(3))
}
