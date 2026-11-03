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
 *
 * A stored list names two formats: its own (`version`, this module's) and that of its
 * entries' criteria (`criteriaVersion`, the search input's {@link HistoryCriteria}). Entries
 * of an older criteria format are converted or left out by the search input. A list of a
 * newer format of either kind was written by a newer version of the application (e.g. in
 * another tab): it is neither read nor written over, and the user is asked to reload the
 * page. Every write stores the current formats, so a list never mixes formats.
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

/**
 * What a search input contributes: its own criteria besides the query text. The history
 * never looks inside them; it stores them, compares them by `key` and hands them back.
 */
export interface HistoryCriteria<C> {
  /** Distinguishes histories of different search inputs, e.g. `search`. */
  namespace: string
  /**
   * The format of the criteria written now, stored with the list. Raise it when what stored
   * criteria mean changes, so older criteria are never read as the new format.
   */
  version: number
  /**
   * The criteria of a stored entry written in format `version` (never newer than the
   * current one), validated and, for an older format, converted; null when malformed or an
   * older format that is not converted (the entry is then left out).
   */
  parse: (raw: unknown, version: number) => C | null
  /** Equal for criteria that run the same search (canonical order of filters and values). */
  key: (criteria: C) => string
}

/**
 * A stored history as read: its usable entries, or `newerFormat` when it was written by a
 * newer version of the application (no entries are read and nothing may be written).
 */
export interface StoredHistory<C> {
  entries: HistoryEntry<C>[]
  newerFormat: boolean
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
export function parseHistory<C> (stored: string | null, criteria: HistoryCriteria<C>): StoredHistory<C> {
  const empty: StoredHistory<C> = { entries: [], newerFormat: false }
  if (!stored) return empty
  let data: unknown
  try {
    data = JSON.parse(stored)
  } catch {
    return empty
  }
  if (!isRecord(data)) return empty
  const { version, criteriaVersion } = data
  if (!isFormat(version) || !isFormat(criteriaVersion)) return empty
  if (version > FORMAT_VERSION || criteriaVersion > criteria.version) return { entries: [], newerFormat: true }
  if (version !== FORMAT_VERSION || !Array.isArray(data.entries)) return empty
  const entries: HistoryEntry<C>[] = []
  const seen = new Set<string>()
  for (const raw of data.entries as unknown[]) {
    const entry = parseEntry(raw, criteriaVersion, criteria)
    if (!entry) continue
    const key = entryKey(entry, criteria)
    if (seen.has(key)) continue
    seen.add(key)
    entries.push(entry)
  }
  return { entries: entries.sort((a, b) => b.savedAt - a.savedAt).slice(0, HISTORY_LIMIT), newerFormat: false }
}

function parseEntry<C> (raw: unknown, criteriaVersion: number, criteria: HistoryCriteria<C>): HistoryEntry<C> | null {
  if (!isRecord(raw)) return null
  const { query, savedAt } = raw
  if (typeof query !== 'string') return null
  const saved = savedQuery(query)
  if (saved === null) return null
  if (typeof savedAt !== 'number' || !Number.isFinite(savedAt)) return null
  const parsed = criteria.parse(raw.criteria, criteriaVersion)
  if (parsed === null) return null
  return { query: saved, criteria: parsed, savedAt }
}

/** The stored form, in the current formats. */
export function serializeHistory<C> (entries: HistoryEntry<C>[], criteria: HistoryCriteria<C>): string {
  return JSON.stringify({
    version: FORMAT_VERSION,
    criteriaVersion: criteria.version,
    entries: entries.map(e => ({ query: e.query, savedAt: e.savedAt, criteria: e.criteria }))
  })
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

export function readHistory<C> (audience: HistoryAudience, criteria: HistoryCriteria<C>): StoredHistory<C> {
  return parseHistory(readStored(storageKey(criteria.namespace, audience)), criteria)
}

export function writeHistory<C> (audience: HistoryAudience, criteria: HistoryCriteria<C>, entries: HistoryEntry<C>[]): void {
  const key = storageKey(criteria.namespace, audience)
  if (entries.length) writeStored(key, serializeHistory(entries, criteria))
  else removeStored(key)
}

/**
 * Changes an audience's history as stored now (another tab may have changed it meanwhile).
 * Returns the history as stored afterwards; a history of a newer format is left unchanged.
 */
export function updateHistory<C> (
  audience: HistoryAudience,
  criteria: HistoryCriteria<C>,
  change: (entries: HistoryEntry<C>[]) => HistoryEntry<C>[]
): StoredHistory<C> {
  const current = readHistory(audience, criteria)
  if (current.newerFormat) return current
  const entries = change(current.entries)
  writeHistory(audience, criteria, entries)
  return { entries, newerFormat: false }
}

/** A format number: a positive integer. */
function isFormat (value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value > 0
}

function isRecord (value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
