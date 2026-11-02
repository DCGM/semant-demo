import { readStored, removeStored, writeStored } from 'src/shared/browserStorage'

/**
 * Recent search history kept in this browser (#558). The list logic and its storage are
 * independent of a page: a search input supplies how its criteria are validated and
 * compared ({@link HistoryCriteria}), the history keeps the entries.
 *
 * Each audience has its own key: one per signed-in user and one for signed-out use. They are
 * never merged. Stored data is untrusted (another tab, an older version or a user may have
 * written it): every entry is validated when read and malformed ones are left out. Storage
 * that is unavailable or full only means nothing is remembered.
 */

/** Entries kept per audience; the oldest is dropped first. */
export const HISTORY_LIMIT = 50
/** Entries shown at once. */
export const DISPLAY_LIMIT = 10
/** Longer queries are not saved (a shortened one would run another search). */
export const MAX_QUERY_LENGTH = 1000

const STORAGE_PREFIX = 'semant.searchHistory.'
const FORMAT_VERSION = 1

/** Whose history: a signed-in user's or the signed-out one. */
export type HistoryAudience = { kind: 'user', userId: string } | { kind: 'anonymous' }

export interface HistoryEntry<C> {
  query: string
  criteria: C
  /** Milliseconds since the epoch of the last time this search was run. */
  savedAt: number
}

/** One entry as a dropdown shows it: its query and a short description of its other criteria. */
export interface SearchHistoryItem {
  key: string
  query: string
  detail: string
}

/** What a search input contributes: its own criteria besides the query text. */
export interface HistoryCriteria<C> {
  /** Distinguishes histories of different search inputs, e.g. `search`. */
  namespace: string
  /** The criteria of a stored entry, or null when they are malformed. */
  parse: (raw: unknown) => C | null
  /** Equal for criteria that run the same search (canonical order of filters and values). */
  key: (criteria: C) => string
}

export function storageKey (namespace: string, audience: HistoryAudience): string {
  const owner = audience.kind === 'user' ? `user.${audience.userId}` : 'anonymous'
  return `${STORAGE_PREFIX}${namespace}.${owner}`
}

/**
 * The query as saved: as typed, without surrounding whitespace, so running it again sends
 * the same text. Null when it is blank or longer than {@link MAX_QUERY_LENGTH}.
 */
export function savedQuery (query: string): string | null {
  const trimmed = query.trim()
  return trimmed && trimmed.length <= MAX_QUERY_LENGTH ? trimmed : null
}

/** The query as compared (for the same search and for matching typed text): whitespace collapsed. */
function comparedQuery (query: string): string {
  return query.trim().replace(/\s+/g, ' ')
}

/** Identity of an entry: equal for the same query (up to whitespace) and criteria. */
export function entryKey<C> (entry: { query: string, criteria: C }, criteria: HistoryCriteria<C>): string {
  return JSON.stringify([comparedQuery(entry.query), criteria.key(entry.criteria)])
}

/** The valid entries of a stored value, newest first, at most {@link HISTORY_LIMIT}. */
export function parseHistory<C> (stored: string | null, criteria: HistoryCriteria<C>): HistoryEntry<C>[] {
  if (!stored) return []
  let data: unknown
  try {
    data = JSON.parse(stored)
  } catch {
    return []
  }
  if (!isRecord(data) || data.version !== FORMAT_VERSION || !Array.isArray(data.entries)) return []
  const entries: HistoryEntry<C>[] = []
  const seen = new Set<string>()
  for (const raw of data.entries as unknown[]) {
    const entry = parseEntry(raw, criteria)
    if (!entry) continue
    const key = entryKey(entry, criteria)
    if (seen.has(key)) continue
    seen.add(key)
    entries.push(entry)
  }
  return entries.sort((a, b) => b.savedAt - a.savedAt).slice(0, HISTORY_LIMIT)
}

function parseEntry<C> (raw: unknown, criteria: HistoryCriteria<C>): HistoryEntry<C> | null {
  if (!isRecord(raw)) return null
  const { query, savedAt } = raw
  if (typeof query !== 'string') return null
  const saved = savedQuery(query)
  if (saved === null) return null
  if (typeof savedAt !== 'number' || !Number.isFinite(savedAt)) return null
  const parsed = criteria.parse(raw.criteria)
  if (parsed === null) return null
  return { query: saved, criteria: parsed, savedAt }
}

export function serializeHistory<C> (entries: HistoryEntry<C>[]): string {
  return JSON.stringify({ version: FORMAT_VERSION, entries })
}

/**
 * The history with `entry` added as the newest; an entry with the same query and criteria
 * is replaced (moved to the top), and the oldest beyond {@link HISTORY_LIMIT} are dropped.
 */
export function withEntry<C> (entries: HistoryEntry<C>[], entry: HistoryEntry<C>, criteria: HistoryCriteria<C>): HistoryEntry<C>[] {
  const key = entryKey(entry, criteria)
  return [entry, ...entries.filter(e => entryKey(e, criteria) !== key)].slice(0, HISTORY_LIMIT)
}

export function withoutEntry<C> (entries: HistoryEntry<C>[], entry: HistoryEntry<C>, criteria: HistoryCriteria<C>): HistoryEntry<C>[] {
  const key = entryKey(entry, criteria)
  return entries.filter(e => entryKey(e, criteria) !== key)
}

/**
 * The newest entries whose query contains `text` (case-insensitive), at most `limit`.
 * Matching covers all stored entries, not only the ones shown without text.
 */
export function matchingEntries<C> (entries: HistoryEntry<C>[], text: string, limit = DISPLAY_LIMIT): HistoryEntry<C>[] {
  const needle = comparedQuery(text).toLocaleLowerCase()
  const matches = needle ? entries.filter(e => comparedQuery(e.query).toLocaleLowerCase().includes(needle)) : entries
  return matches.slice(0, limit)
}

export function readHistory<C> (audience: HistoryAudience, criteria: HistoryCriteria<C>): HistoryEntry<C>[] {
  return parseHistory(readStored(storageKey(criteria.namespace, audience)), criteria)
}

export function writeHistory<C> (audience: HistoryAudience, criteria: HistoryCriteria<C>, entries: HistoryEntry<C>[]): void {
  const key = storageKey(criteria.namespace, audience)
  if (entries.length) writeStored(key, serializeHistory(entries))
  else removeStored(key)
}

function isRecord (value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
