/** A plain text segment between (or around) citation markers. */
export interface TextToken { type: 'text'; value: string }

/**
 * Splits `text` into alternating text and citation tokens around `[docN]` markers — the
 * citation convention both the search-results and document summarizers use (#358 review:
 * `useSearchSummary.parseSummaryTokens` and `useDocumentSummary.parseDocumentSummaryTokens`
 * had near-identical copies of this loop, differing only in how a matched number resolves
 * into a citation).
 *
 * `resolveCitation` turns a matched citation number into that citation token's extra fields.
 * A `null` result renders the marker as plain text instead of a citation with nothing behind
 * it — used by document summaries, where a citation the response didn't actually send (model
 * output, so not guaranteed) must not become a dead link; search summaries always resolve to
 * some number, so never return `null`.
 */
export function tokenizeCitations<Citation extends object> (
  text: string,
  resolveCitation: (number: number) => Citation | null
): Array<TextToken | ({ type: 'citation' } & Citation)> {
  const tokens: Array<TextToken | ({ type: 'citation' } & Citation)> = []
  const citationRegex = /\[(doc([1-9][0-9]*))]/g
  let lastIndex = 0

  for (const match of text.matchAll(citationRegex)) {
    const matchText = match[0]
    const number = parseInt(match[2], 10)
    const index = match.index ?? 0

    if (index > lastIndex) {
      tokens.push({ type: 'text', value: text.slice(lastIndex, index) })
    }
    const citation = resolveCitation(number)
    tokens.push(citation ? { type: 'citation', ...citation } : { type: 'text', value: matchText })

    lastIndex = index + matchText.length
  }

  if (lastIndex < text.length) {
    tokens.push({ type: 'text', value: text.slice(lastIndex) })
  }

  return tokens
}
