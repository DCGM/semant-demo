import type { Attribute, AttributeValue } from 'src/generated/api'
import { orderedValues, valueName } from './attributeForm'

/** A piece of a text that matches the search, or lies between matches. */
export type TextPart = { text: string, match: boolean }

const normalize = (text: string | null | undefined) => (text ?? '').trim().toLowerCase()

/** The text cut into pieces at each match of `needle`, ignoring case; one plain piece without a
 * needle or a match. */
export function matchParts (text: string, needle: string | null | undefined): TextPart[] {
  const wanted = normalize(needle)
  if (!wanted) return [{ text, match: false }]
  const parts: TextPart[] = []
  const lower = text.toLowerCase()
  let from = 0
  for (let at = lower.indexOf(wanted); at >= 0; at = lower.indexOf(wanted, at + wanted.length)) {
    if (at > from) parts.push({ text: text.slice(from, at), match: false })
    parts.push({ text: text.slice(at, at + wanted.length), match: true })
    from = at + wanted.length
  }
  if (from < text.length) parts.push({ text: text.slice(from), match: false })
  return parts.length ? parts : [{ text, match: false }]
}

export const matches = (text: string, needle: string | null | undefined) => {
  const wanted = normalize(needle)
  return !!wanted && text.toLowerCase().includes(wanted)
}

export type ShownAttribute = {
  attribute: Attribute
  /** The values to show: the matching ones first, then the others, each in their order. */
  values: AttributeValue[]
  nameMatches: boolean
  matchingValues: number
}

export type AttributeSearch = {
  shown: ShownAttribute[]
  /** Matches the Show retired setting hides: a retired attribute counts once, a retired value of
   * a shown attribute once each. */
  hiddenMatches: number
}

/** The attributes to list for a search over attribute names and value names (#506). Without a
 * search, every attribute; with one, those whose name or a value matches. Retired ones only
 * with `showRetired`: a match the setting hides is counted in `hiddenMatches`, never shown. */
export function searchAttributes (attributes: Attribute[], needle: string | null | undefined,
  showRetired: boolean): AttributeSearch {
  const searching = !!normalize(needle)
  const shown: ShownAttribute[] = []
  let hiddenMatches = 0
  for (const attribute of attributes) {
    const nameMatches = matches(attribute.name, needle)
    const all = orderedValues(attribute)
    const matching = all.filter(v => matches(valueName(v), needle))
    if (attribute.retired && !showRetired) {
      if (nameMatches || matching.length) hiddenMatches++
      continue
    }
    const visible = showRetired ? all : all.filter(v => !v.retired)
    const visibleMatching = visible.filter(v => matching.includes(v))
    hiddenMatches += matching.length - visibleMatching.length
    if (searching && !nameMatches && !visibleMatching.length) continue
    shown.push({
      attribute,
      values: [...visibleMatching, ...visible.filter(v => !visibleMatching.includes(v))],
      nameMatches,
      matchingValues: visibleMatching.length
    })
  }
  return { shown, hiddenMatches }
}
