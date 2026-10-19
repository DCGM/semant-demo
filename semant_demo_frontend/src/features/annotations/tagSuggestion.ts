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

/**
 * Strings to compare tag names against: the whole selection, each word, and each adjacent
 * word pair — covers multi-word tag names (e.g. "Jan Novák").
 */
function candidatesFrom(words: string[], trimmed: string): string[] {
  const candidates = [trimmed, ...words]
  for (let i = 0; i < words.length - 1; i++) candidates.push(`${words[i]} ${words[i + 1]}`)
  return candidates.filter((c) => c.length > 0 && c.length <= MAX_CANDIDATE_LENGTH)
}

/**
 * Ranks `tags` by how closely their name/shorthand resembles the selected text — a cheap,
 * client-side stand-in for "is this tag likely what the user just highlighted", good enough for
 * short tag names without any usage-tracking state. Returns ids scoring above a minimum
 * similarity, best match first.
 *
 * Only runs for short selections (at most `MAX_SELECTION_WORDS` words): beyond that, a highlighted
 * passage is prose rather than something resembling a tag name, so the comparison stops being
 * meaningful and isn't worth the (still cheap, but pointless) extra work.
 */
export function suggestTagIds(selectedText: string | null | undefined, tags: Tag[], limit = 3): string[] {
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
    .slice(0, limit)
    .map((t) => t.id)
}

/**
 * The popover's full suggestion list: the collection's last-used tag first (if it still exists),
 * then any text-similarity matches not already included, best match first.
 */
export function buildTagSuggestions(
  selectedText: string | null | undefined,
  tags: Tag[],
  lastUsedTagId: string | null | undefined,
  limit = 3
): string[] {
  const result: string[] = []
  if (lastUsedTagId && tags.some((t) => t.id === lastUsedTagId)) result.push(lastUsedTagId)
  for (const id of suggestTagIds(selectedText, tags, limit)) {
    if (result.length >= limit) break
    if (!result.includes(id)) result.push(id)
  }
  return result
}
