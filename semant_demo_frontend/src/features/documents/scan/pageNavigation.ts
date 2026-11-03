// Page and line navigation of the scan viewer, independent of the components.

import type { DocumentPage } from 'src/generated/api'
import type { ScanLine } from './pageLayout'

const TYPE_NAMES: Record<string, string> = {
  FrontCover: 'front cover',
  BackCover: 'back cover',
  Blank: 'blank page',
  TitlePage: 'title page',
  FrontEndSheet: 'front endsheet',
  BackEndSheet: 'back endsheet'
}

/** The accessible name of a page: its printed label (or position) and special type. */
export function pageName (page: DocumentPage, index: number): string {
  const name = `Page ${page.label ?? index + 1}`
  const type = page.pageType ? TYPE_NAMES[page.pageType] : undefined
  return type ? `${name}, ${type}` : name
}

/**
 * The index of the page a user typed: a printed label first (e.g. `[1]`, `6`, `IV`, also
 * without its brackets), else a position in the page list (1 = the first page). Null when
 * nothing matches.
 */
export function findPage (pages: readonly DocumentPage[], query: string): number | null {
  const q = query.trim()
  if (!q) return null
  const norm = (s: string) => s.trim().toLowerCase()
  const exact = pages.findIndex(p => p.label !== null && p.label !== undefined && norm(p.label) === norm(q))
  if (exact >= 0) return exact
  const bare = (s: string) => norm(s).replace(/^\[(.*)\]$/, '$1')
  const unbracketed = pages.findIndex(p => p.label !== null && p.label !== undefined && bare(p.label) === bare(q))
  if (unbracketed >= 0) return unbracketed
  if (/^\d+$/.test(q)) {
    const position = Number(q)
    if (position >= 1 && position <= pages.length) return position - 1
  }
  return null
}

/**
 * The line `step` lines after `currentId` in serialization order; the first (forward) or
 * last (backward) line when none is current; null past either end.
 */
export function adjacentLine (lines: readonly ScanLine[], currentId: string | null, step: 1 | -1): ScanLine | null {
  if (!lines.length) return null
  const index = currentId === null ? -1 : lines.findIndex(l => l.id === currentId)
  if (index < 0) return step > 0 ? lines[0] : lines[lines.length - 1]
  return lines[index + step] ?? null
}
