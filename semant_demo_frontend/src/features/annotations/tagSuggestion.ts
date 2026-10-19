import type { Tag } from 'src/generated/api'

/** Classic Levenshtein edit distance. Only ever called on short strings (tag names, single words). */
function levenshtein(a: string, b: string): number {
  if (a === b) return 0
  const m = a.length
  const n = b.length
  if (m === 0) return n
  if (n === 0) return m

  let prev = Array.from({ length: n + 1 }, (_, j) => j)
  const curr = new Array(n + 1).fill(0)
  for (let i = 1; i <= m; i++) {
    curr[0] = i
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1
      curr[j] = Math.min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
    }
    prev = [...curr]
  }
  return prev[n]
}

/** 0 (nothing alike) .. 1 (identical), case/whitespace-insensitive. */
function similarity(a: string, b: string): number {
  const x = a.trim().toLowerCase()
  const y = b.trim().toLowerCase()
  if (!x || !y) return 0
  return 1 - levenshtein(x, y) / Math.max(x.length, y.length)
}

const MAX_CANDIDATE_LENGTH = 60
const MAX_SELECTION_WORDS = 5
const MIN_SCORE = 0.5
// With few enough tags, finding the right one is not a problem a suggestion needs to solve —
// below this, the popover shows the plain alphabetical list and nothing else.
const MIN_TAGS_FOR_SUGGESTIONS = 6

/**
 * Strings to compare tag names against: the whole selection, each word, and each adjacent
 * word pair — covers multi-word tag names (e.g. "Jan Novák").
 */
function candidatesFrom(words: string[], trimmed: string): string[] {
  const candidates = [trimmed, ...words]
  for (let i = 0; i < words.length - 1; i++) candidates.push(`${words[i]} ${words[i + 1]}`)
  return candidates.filter((c) => c.length > 0 && c.length <= MAX_CANDIDATE_LENGTH)
}

interface ScoredTag {
  id: string
  /** 0..1 text similarity between the selection and the tag's name/shorthand. */
  score: number
}

/**
 * Ranks `tags` by how closely their name/shorthand resembles the selected text — a cheap,
 * client-side stand-in for "is this tag likely what the user just highlighted", good enough for
 * short tag names without any usage-tracking state. Returns tags scoring above a minimum
 * similarity, best match first.
 *
 * Only runs for short selections (at most `MAX_SELECTION_WORDS` words): beyond that, a highlighted
 * passage is prose rather than something resembling a tag name, so the comparison stops being
 * meaningful and isn't worth the (still cheap, but pointless) extra work.
 */
function scoreTagsBySimilarity(selectedText: string | null | undefined, tags: Tag[]): ScoredTag[] {
  const trimmed = selectedText?.trim()
  if (!trimmed || !tags.length) return []
  const words = trimmed.split(/\s+/).filter(Boolean)
  if (words.length > MAX_SELECTION_WORDS) return []
  const candidates = candidatesFrom(words, trimmed)

  return tags
    .map((tag) => {
      const names = [tag.name, tag.shorthand].filter((n): n is string => !!n)
      let best = 0
      for (const name of names) {
        for (const candidate of candidates) {
          const score = similarity(candidate, name)
          if (score > best) best = score
        }
      }
      return { id: tag.id, score: best }
    })
    .filter((t) => t.score >= MIN_SCORE)
    .sort((a, b) => b.score - a.score)
}

/** Ids of `scoreTagsBySimilarity`'s top matches, best first — the `score` without its numbers. */
export function suggestTagIds(selectedText: string | null | undefined, tags: Tag[], limit = 3): string[] {
  return scoreTagsBySimilarity(selectedText, tags).slice(0, limit).map((t) => t.id)
}

export interface TagSuggestion {
  id: string
  /**
   * The text-similarity score (0..1) behind this suggestion, or `null` when it is suggested
   * purely because it was last used — it may still also resemble the selection, just not closely
   * enough to have been found by similarity on its own.
   */
  score: number | null
}

/**
 * The popover's full suggestion list: the collection's last-used tag first (if it still exists),
 * then any text-similarity matches not already included, best match first. Empty once the
 * collection has too few tags for a suggestion to be worth showing at all.
 */
export function buildTagSuggestions(
  selectedText: string | null | undefined,
  tags: Tag[],
  lastUsedTagId: string | null | undefined,
  limit = 3
): TagSuggestion[] {
  if (tags.length < MIN_TAGS_FOR_SUGGESTIONS) return []

  const scored = scoreTagsBySimilarity(selectedText, tags)
  const scoreById = new Map(scored.map((t) => [t.id, t.score]))
  const result: TagSuggestion[] = []

  if (lastUsedTagId && tags.some((t) => t.id === lastUsedTagId)) {
    result.push({ id: lastUsedTagId, score: scoreById.get(lastUsedTagId) ?? null })
  }
  for (const { id, score } of scored) {
    if (result.length >= limit) break
    if (!result.some((r) => r.id === id)) result.push({ id, score })
  }
  return result
}
