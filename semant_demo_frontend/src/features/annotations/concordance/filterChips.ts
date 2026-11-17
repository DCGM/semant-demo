import {
  DistanceUnit, NearDirection, NearRelation, RetrievalMode, SpanType, TextScope, type AnnotatedDocument, type AnnotationListRow,
  type Attribute, type NearFilter, type Tag
} from 'src/generated/api'
import { filterGroups, withoutFilter } from 'src/features/analytics/corpusOverview'
import { orderedValues, valueName } from 'src/features/attributes/attributeForm'
import { defaultFilters, modeChange, type ConcordanceFilters } from './concordanceStore'

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

/** The retrieval modes (#664), as the mode selector names them. */
export const MODE_LABELS: Record<RetrievalMode, string> = {
  [RetrievalMode.lexical]: 'Words',
  [RetrievalMode.semantic]: 'Meaning',
  [RetrievalMode.hybrid]: 'Meaning and words',
  [RetrievalMode.similar]: 'Similar'
}

/** How a ranked mode ranks, for the result label, e.g. "Top 100 by meaning". */
const RANKED_BY: Record<RetrievalMode, string> = {
  [RetrievalMode.lexical]: '',
  [RetrievalMode.semantic]: 'by meaning',
  [RetrievalMode.hybrid]: 'by meaning and words',
  [RetrievalMode.similar]: 'most similar'
}

/** What the mode's text field does, as its hint says. */
export function modeHintText (mode: RetrievalMode, scope: TextScope): string {
  if (mode === RetrievalMode.semantic) {
    return 'Ranks annotations with their context by closeness in meaning to this text; it filters nothing.'
  }
  if (mode === RetrievalMode.hybrid) {
    return `Ranks by meaning and by the words found in ${SCOPE_FIELDS[scope]} (BM25), equally weighted; it filters nothing.`
  }
  return scopeHintText(scope)
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

/** A text or context sorted page's note on rows without a current sort key (#666), e.g. "3
 * annotations are not sortable yet and are listed first"; null when every row has one. Rows
 * without a key are placed by Weaviate: first ascending, last descending. */
export function unsortableLabel (unsortable: number | null | undefined, descending: boolean): string | null {
  if (!unsortable) return null
  const subject = unsortable === 1 ? '1 annotation is' : `${unsortable} annotations are`
  return `${subject} not sortable yet and listed ${descending ? 'last' : 'first'}`
}

/** Where a neighbor lies (#333), one choice per relation and side, as the proximity form offers them. */
export const PLACEMENTS: { key: string, label: string, relation: NearRelation, direction: NearDirection, phrase: string }[] = [
  { key: 'near', label: 'on either side', relation: NearRelation.within, direction: NearDirection.either, phrase: '' },
  { key: 'before', label: 'before it', relation: NearRelation.within, direction: NearDirection.before, phrase: 'before' },
  { key: 'after', label: 'after it', relation: NearRelation.within, direction: NearDirection.after, phrase: 'after' },
  { key: 'overlaps', label: 'overlapping it', relation: NearRelation.overlaps, direction: NearDirection.either, phrase: 'overlapping' },
  { key: 'inside', label: 'inside it', relation: NearRelation.contains, direction: NearDirection.either, phrase: 'inside' },
  { key: 'containing', label: 'containing it', relation: NearRelation.containedBy, direction: NearDirection.either, phrase: 'containing' },
  { key: 'document', label: 'anywhere in the document', relation: NearRelation.sameDocument, direction: NearDirection.either, phrase: 'in the same document' }
]

/** The form's choice of a proximity filter's relation and side. */
export function placementOf (near: NearFilter): string {
  const relation = near.relation ?? NearRelation.within
  const direction = relation === NearRelation.within ? (near.direction ?? NearDirection.either) : NearDirection.either
  return PLACEMENTS.find(p => p.relation === relation && p.direction === direction)?.key ?? 'near'
}

export const UNIT_LABELS: Record<DistanceUnit, string> = {
  [DistanceUnit.words]: 'words',
  [DistanceUnit.chars]: 'characters'
}

/** The default proximity filter: a neighbor of `tagIds` within 50 words on either side. */
export function defaultNear (tagIds: string[]): NearFilter {
  return { tagIds, relation: NearRelation.within, distance: 50, unit: DistanceUnit.words, direction: NearDirection.either, absent: false }
}

/** How the neighbor must lie, e.g. "within 50 words after" or "overlapping". */
export function nearRelationText (near: NearFilter): string {
  const placement = PLACEMENTS.find(p => p.key === placementOf(near))!
  if (placement.relation !== NearRelation.within) return placement.phrase
  const side = placement.phrase ? ` ${placement.phrase}` : ''
  return `within ${near.distance ?? 50} ${UNIT_LABELS[near.unit ?? DistanceUnit.words]}${side}`
}

const NEIGHBOR_PLACES: Record<string, string> = {
  overlaps: 'that overlaps it',
  inside: 'inside it',
  containing: 'that contains it',
  document: 'anywhere in the same document'
}

/** The proximity filter as one sentence, so "Without" reads as what it is: a negation (#333). */
export function nearSummary (near: NearFilter | null | undefined, primaryTags: string[], neighborTags: string[]): string {
  if (!near) return 'Choose neighbor tags to keep only annotations with, or without, such an annotation nearby in the same document.'
  const listed = primaryTags.length ? `${primaryTags.join(' or ')} annotations` : 'annotations'
  const neighbor = neighborTags.length ? `annotation tagged ${neighborTags.join(' or ')}` : 'annotation of any tag'
  const key = placementOf(near)
  const distance = `${near.distance ?? 50} ${UNIT_LABELS[near.unit ?? DistanceUnit.words]}`
  const where = NEIGHBOR_PLACES[key] ?? (key === 'before'
    ? `ending at most ${distance} before it`
    : key === 'after' ? `starting at most ${distance} after it` : `at most ${distance} away`)
  return `Shows ${listed} that have ${near.absent ? 'no' : 'an'} ${neighbor} ${where}. ` +
    'Annotations whose position is not known yet are left out.'
}

const MIRRORED_DIRECTION: Record<NearDirection, NearDirection> = {
  [NearDirection.either]: NearDirection.either,
  [NearDirection.before]: NearDirection.after,
  [NearDirection.after]: NearDirection.before
}

const MIRRORED_RELATION: Partial<Record<NearRelation, NearRelation>> = {
  [NearRelation.contains]: NearRelation.containedBy,
  [NearRelation.containedBy]: NearRelation.contains
}

/**
 * The filter change that swaps the listed annotations and their neighbors (#333): "Statement near
 * Criticism" becomes "Criticism near Statement". The tags, statuses and attribute values of the two
 * sides are exchanged and the relation is mirrored (a neighbor after a Statement means a Statement
 * before the neighbor; inside and containing exchange). The other filters (text, sources, "not
 * assigned" attributes, document filters) stay with the listed annotations. Null without a
 * proximity filter or listed tags.
 */
export function swapNear (f: ConcordanceFilters): Partial<ConcordanceFilters> | null {
  const near = f.near
  if (!near?.tagIds?.length || !f.tagIds.length) return null
  const relation = near.relation ?? NearRelation.within
  return {
    tagIds: [...near.tagIds],
    types: near.types?.length ? [...near.types] : defaultFilters().types,
    attributeValues: [...(near.attributeValues ?? [])],
    near: {
      ...near,
      tagIds: [...f.tagIds],
      types: [...f.types],
      attributeValues: [...f.attributeValues],
      relation: MIRRORED_RELATION[relation] ?? relation,
      direction: MIRRORED_DIRECTION[near.direction ?? NearDirection.either]
    }
  }
}

/** What the proximity filter could not compare (#333), e.g. "3 annotations without current positions
 * were not compared"; null when everything was compared. */
export function proximityLabel (coverage: { unknown: number, neighborsUnpositioned: number } | null | undefined): string | null {
  if (!coverage) return null
  const parts: string[] = []
  if (coverage.unknown) {
    parts.push(`${coverage.unknown} ${coverage.unknown === 1 ? 'annotation' : 'annotations'} with unknown positions left out`)
  }
  if (coverage.neighborsUnpositioned) {
    parts.push(`${coverage.neighborsUnpositioned} ${coverage.neighborsUnpositioned === 1 ? 'neighbor' : 'neighbors'} with unknown positions not compared`)
  }
  return parts.length ? `Proximity: ${parts.join(', ')}` : null
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
    chips.push({ key: 'similar', group: 'Similar to', label: sourceLabel(f.similarTo), remove: modeChange(RetrievalMode.lexical), opens: f.similarTo })
  }
  if (f.text.trim()) {
    const group = f.mode === RetrievalMode.semantic
      ? 'Meaning'
      : f.mode === RetrievalMode.hybrid ? `Meaning and words in ${SCOPE_LABELS[f.textScope].toLowerCase()}` : `Text in ${SCOPE_LABELS[f.textScope].toLowerCase()}`
    chips.push({ key: 'text', group, label: f.text.trim(), remove: { text: '' } })
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
  if (f.near) {
    const names = (f.near.tagIds ?? []).map(id => tagNames.get(id) ?? 'Unknown tag')
    chips.push({
      key: 'near',
      group: f.near.absent ? 'Not near' : 'Near',
      label: `${names.length ? names.join(', ') : 'any tag'} ${nearRelationText(f.near)}`,
      remove: { near: null }
    })
  }
  return chips
}
