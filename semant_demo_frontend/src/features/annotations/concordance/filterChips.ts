import {
  RetrievalMode, SpanType, TextScope, type AnnotatedDocument, type AnnotationListRow, type Attribute, type Tag
} from 'src/generated/api'
import { filterGroups, withoutFilter } from 'src/features/analytics/corpusOverview'
import { orderedValues, valueName } from 'src/features/attributes/attributeForm'
import { clearSimilar, defaultFilters, type ConcordanceFilters } from './concordanceStore'

/** The fields of a lexical annotation query (#663), as the scope selector names them. */
export const SCOPE_LABELS: Record<TextScope, string> = {
  [TextScope.annotation]: 'Annotation',
  [TextScope.context]: 'Context',
  [TextScope.both]: 'Both'
}

const SCOPE_FIELDS: Record<TextScope, string> = {
  [TextScope.annotation]: 'the annotation',
  [TextScope.context]: 'the left or right context',
  [TextScope.both]: 'the annotation or its context'
}

/** What a lexical query matches, exactly as the server evaluates it (`TextScope`). */
export function scopeHintText (scope: TextScope): string {
  const where = SCOPE_FIELDS[scope]
  const several = scope === TextScope.annotation ? '' : ' Different words may occur in different fields.'
  return `Each word must appear inside a word of ${where}, ignoring case but not diacritics.${several} ` +
    'Not a phrase search.'
}

const MAX_TITLES = 10
const MAX_TITLE_WORDS = 5
const TITLE_WORD = /[\p{L}\p{N}]+/gu

/** The server's title-filter rules (`DocumentFilters.title_contains`), checked before adding one. */
export function titleProblem (text: string, titles: string[]): string | null {
  if (/[*?]/.test(text)) return 'Wildcards (* or ?) are not supported; enter whole or partial words'
  const words = (text.match(TITLE_WORD) ?? []).filter(w => w.length >= 2)
  if (!words.length) return 'Enter at least one word of two or more letters or digits'
  if (new Set(words.map(w => w.toLowerCase())).size > MAX_TITLE_WORDS) return `At most ${MAX_TITLE_WORDS} words`
  return titles.length < MAX_TITLES ? null : `At most ${MAX_TITLES} titles`
}

export interface ConcordanceChip {
  /** Unique within the list. */
  key: string
  /** The kind of filter, e.g. "Tag". */
  group: string
  label: string
  /** The change of the filters that removes this chip. */
  remove: Partial<ConcordanceFilters>
  /** A reference chip: clicking it opens this annotation (the source of Find similar). */
  opens?: AnnotationListRow
}

/** How a ranked mode ranks, for the result label, e.g. "Top 100 by meaning". */
const RANKED_BY: Record<RetrievalMode, string> = {
  [RetrievalMode.lexical]: '',
  [RetrievalMode.semantic]: 'by meaning',
  [RetrievalMode.hybrid]: 'by meaning and words',
  [RetrievalMode.similar]: 'most similar'
}

/** What the Similarity field does, as its hint says (#716). */
export function similarityHintText (scope: TextScope): string {
  return 'Ranks the annotations matching the filters (words included) by meaning and by these words found in ' +
    `${SCOPE_FIELDS[scope]} (BM25), equally weighted; shows a bounded top list and filters nothing.`
}

/** The source annotation of Find similar, quoted and shortened. */
export function sourceLabel (row: AnnotationListRow): string {
  const text = (row.text ?? '').trim() || 'annotation'
  return `'${text.length > 40 ? `${text.slice(0, 39)}…` : text}'`
}

/** The description of a ranked page (#664), e.g. "Top 100 by meaning · 37 matching annotations
 * have no vector yet"; null for a complete (lexical) result. */
export function rankedLabel (result: { kind?: string, mode?: RetrievalMode, k?: number | null, truncated?: boolean,
  coverage?: { matching: number, withVector: number } | null } | undefined, returned: number): string | null {
  if (!result || result.kind !== 'top_k' || !result.mode) return null
  const parts = [`Top ${result.k ?? returned} ${RANKED_BY[result.mode]}`]
  if (returned < (result.k ?? 0)) parts[0] += ` (${returned} found)`
  else if (!result.truncated) parts[0] += ' (all that could be ranked)'
  const coverage = result.coverage
  if (coverage) {
    const missing = coverage.matching - coverage.withVector
    if (missing > 0) {
      parts.push(`${missing} matching ${missing === 1 ? 'annotation has' : 'annotations have'} no vector yet and cannot be ranked`)
    }
  }
  return parts.join(' · ')
}

const STATUS_LABELS: Record<SpanType, string> = {
  [SpanType.pos]: 'Confirmed',
  [SpanType.auto]: 'Proposals',
  [SpanType.neg]: 'Rejected'
}

/**
 * Every active filter of the concordance as a removable chip, in the toolbar's order (#663).
 * The status chip appears only when the statuses differ from the default (confirmed and
 * proposals); removing it restores the default.
 */
export function concordanceChips (f: ConcordanceFilters, tags: Tag[], documents: AnnotatedDocument[],
  attributes: Attribute[]): ConcordanceChip[] {
  const chips: ConcordanceChip[] = []
  const tagNames = new Map(tags.map(t => [t.id, t.name]))
  for (const id of f.tagIds) {
    chips.push({ key: `tag:${id}`, group: 'Tag', label: tagNames.get(id) ?? 'Unknown tag', remove: { tagIds: f.tagIds.filter(t => t !== id) } })
  }
  const defaults = defaultFilters()
  if (JSON.stringify([...f.types].sort()) !== JSON.stringify([...defaults.types].sort())) {
    chips.push({ key: 'types', group: 'Status', label: f.types.map(t => STATUS_LABELS[t]).join(', '), remove: { types: defaults.types } })
  }
  if (f.mode === RetrievalMode.similar && f.similarTo) {
    chips.push({ key: 'similar', group: 'Similar to', label: sourceLabel(f.similarTo), remove: clearSimilar(), opens: f.similarTo })
  }
  if (f.text.trim()) {
    chips.push({ key: 'text', group: `Words in ${SCOPE_LABELS[f.textScope].toLowerCase()}`, label: f.text.trim(), remove: { text: '' } })
  }
  if (f.mode === RetrievalMode.hybrid) {
    chips.push({ key: 'similarity', group: 'Similarity', label: f.similarity.trim(), remove: { similarity: '' } })
  }
  const titles = new Map(documents.map(d => [d.id, d.available ? (d.title || 'Untitled document') : 'Unavailable source']))
  for (const id of f.documentIds) {
    chips.push({ key: `document:${id}`, group: 'Source', label: titles.get(id) ?? 'Source', remove: { documentIds: f.documentIds.filter(d => d !== id) } })
  }
  for (const group of filterGroups(f.documentFilters)) {
    for (const chip of group.chips) {
      chips.push({
        key: `${group.key}:${chip.value ?? ''}`,
        group: group.label,
        label: chip.label,
        remove: { documentFilters: withoutFilter(f.documentFilters, group.key, chip.value) }
      })
    }
  }
  const byId = new Map(attributes.map(a => [a.id, a]))
  for (const pair of f.attributeValues) {
    const [attributeId, valueId] = pair.split(':')
    const attribute = byId.get(attributeId)
    const value = attribute && orderedValues(attribute).find(v => v.id === valueId)
    chips.push({
      key: `attribute:${pair}`,
      group: attribute?.name ?? 'Attribute',
      label: value ? valueName(value) : 'Unknown value',
      remove: { attributeValues: f.attributeValues.filter(v => v !== pair) }
    })
  }
  for (const attributeId of f.attributeUnassigned) {
    chips.push({
      key: `unassigned:${attributeId}`,
      group: byId.get(attributeId)?.name ?? 'Attribute',
      label: 'not assigned',
      remove: { attributeUnassigned: f.attributeUnassigned.filter(a => a !== attributeId) }
    })
  }
  return chips
}
