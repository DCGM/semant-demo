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
      head.push({ text: part.text.slice(0, at - position), match: part.match })
      tail.push({ text: part.text.slice(at - position), match: part.match })
    }
    position = end
  }
  return [head, tail]
}
