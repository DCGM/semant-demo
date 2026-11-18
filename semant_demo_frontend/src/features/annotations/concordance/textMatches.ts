/**
 * The lexical matches of a concordance query in a row's text (#663), found the way the server
 * matches them: a query word matches inside a word of the text (a run of letters and digits),
 * ignoring case. The browser only marks them; it never decides which rows match. Text whose
 * words the browser splits differently than Weaviate (e.g. decomposed letters) may stay
 * unmarked, never wrongly marked as something the server did not match.
 */

export interface TextPart {
  text: string
  match: boolean
  /** Part of a neighbor annotation that made the row match the proximity filter (#333): its tag's
   * color and a label. */
  near?: { color: string, label: string }
}

/** A neighbor annotation's range within one field of a row, in UTF-16 offsets of that field. */
export interface NeighborRange {
  start: number
  end: number
  color: string
  label: string
}

/**
 * `parts` (one field of a row, e.g. the left context) with the characters of `ranges` marked
 * as neighbors (#333); ranges outside the field are ignored, overlapping ones keep the first
 * (nearest) neighbor.
 */
export function markNeighbors (parts: TextPart[], ranges: NeighborRange[]): TextPart[] {
  const length = parts.reduce((n, p) => n + p.text.length, 0)
  const inField = ranges
    .map(r => ({ ...r, start: Math.max(0, r.start), end: Math.min(length, r.end) }))
    .filter(r => r.start < r.end)
  if (!inField.length) return parts
  const owner = new Array<NeighborRange | undefined>(length)
  for (const range of inField) {
    for (let i = range.start; i < range.end; i++) owner[i] ??= range
  }
  const result: TextPart[] = []
  let position = 0
  for (const part of parts) {
    let from = 0
    for (let i = 1; i <= part.text.length; i++) {
      if (i === part.text.length || owner[position + i] !== owner[position + from]) {
        const range = owner[position + from]
        result.push({ text: part.text.slice(from, i), match: part.match, ...(range ? { near: { color: range.color, label: range.label } } : {}) })
        from = i
      }
    }
    position += part.text.length
  }
  return result
}

const WORD = /[\p{L}\p{N}]+/gu

/** The query's words as the server searches them (composed, at most 10). */
export function queryWords (query: string): string[] {
  return (query.normalize('NFC').match(WORD) ?? []).slice(0, 10)
}

/**
 * `text` in parts, the occurrences of any of `words` inside its words marked. Several
 * occurrences in one word are each marked; overlapping ones are joined.
 */
export function markMatches (text: string, words: string[]): TextPart[] {
  if (!text || !words.length) return text ? [{ text, match: false }] : []
  const needles = words.map(w => w.toLocaleLowerCase())
  const marked = new Array<boolean>(text.length).fill(false)
  for (const found of text.matchAll(WORD)) {
    const word = found[0]
    const lower = word.toLocaleLowerCase()
    // Lowercasing may change the length (rare letters): such a word is left unmarked.
    if (lower.length !== word.length) continue
    for (const needle of needles) {
      for (let at = lower.indexOf(needle); at >= 0; at = lower.indexOf(needle, at + 1)) {
        marked.fill(true, found.index + at, found.index + at + needle.length)
      }
    }
  }
  const parts: TextPart[] = []
  let start = 0
  for (let i = 1; i <= text.length; i++) {
    if (i === text.length || marked[i] !== marked[start]) {
      parts.push({ text: text.slice(start, i), match: marked[start] })
      start = i
    }
  }
  return parts
}

/**
 * `parts` split into the halves before and after the middle of their text, never inside a
 * surrogate pair: a long annotation shows the start of its first half and the end of its second
 * one, cut in the middle (#665).
 */
export function splitParts (parts: TextPart[]): [TextPart[], TextPart[]] {
  const text = parts.map(p => p.text).join('')
  let at = Math.ceil(text.length / 2)
  if (at < text.length && /[\uDC00-\uDFFF]/.test(text[at])) at++
  const head: TextPart[] = []
  const tail: TextPart[] = []
  let position = 0
  for (const part of parts) {
    const end = position + part.text.length
    if (end <= at) head.push(part)
    else if (position >= at) tail.push(part)
    else {
      head.push({ ...part, text: part.text.slice(0, at - position) })
      tail.push({ ...part, text: part.text.slice(at - position) })
    }
    position = end
  }
  return [head, tail]
}
