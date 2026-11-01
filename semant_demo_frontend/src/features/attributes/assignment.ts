import { AssignMode, Cardinality, SpanType, type Attribute, type AttributeValue } from 'src/generated/api'
import { isSpecial, orderedValues, valueName } from './attributeForm'
import type { AssignReport } from './attributeAssignStore'
import { plural } from 'src/shared/plural'

/** One assignment of values of one attribute (ADR 0011): what the assign route sends besides
 * the annotations. */
export interface AssignChange {
  mode: AssignMode
  valueIds: string[]
}

/** What an annotation holds of an attribute, as the workspace shows it: a known value, or an
 * id the attribute no longer defines (deleted meanwhile, ADR 0011). */
export type HeldValue = { id: string, value: AttributeValue | null }

/** In the attribute's order (ordinary values, then Unknown / Not applicable), whatever order they
 * were assigned in; ids it no longer defines last. */
export function heldValues (attribute: Attribute, ids: string[] | undefined): HeldValue[] {
  const held = new Set(ids ?? [])
  const known = orderedValues(attribute).filter(v => held.has(v.id))
  const defined = new Set(known.map(v => v.id))
  return [
    ...known.map(value => ({ id: value.id, value })),
    ...(ids ?? []).filter(id => !defined.has(id)).map(id => ({ id, value: null }))
  ]
}

export const heldName = (held: HeldValue) => held.value ? valueName(held.value) : 'Unknown value'

/** Whether the attribute applies to the annotation's tag (values kept after a retag may not, #500). */
export const applies = (attribute: Attribute, row: { tagId?: string | null }) =>
  !!attribute.allTags || (!!row.tagId && !!attribute.tagIds?.includes(row.tagId))

/** Why an annotation cannot take values of the attribute now, or null when it can. */
export function cannotAssign (attribute: Attribute, row: { type?: SpanType | null, tagId?: string | null }): string | null {
  if (attribute.retired) return 'This attribute is retired.'
  if (row.type !== SpanType.pos) return 'Only confirmed annotations take attribute values.'
  if (!applies(attribute, row)) return 'This attribute does not apply to the annotation\'s tag.'
  return null
}

/** The values a picker offers: those not retired, and retired ones the annotation still holds
 * (they can only be removed). */
export function offeredValues (attribute: Attribute, current: string[]): AttributeValue[] {
  const held = new Set(current)
  return orderedValues(attribute).filter(v => !v.retired || held.has(v.id))
}

/**
 * The assignment that checking (`checked`) or unchecking one value of an annotation means.
 * A single-valued attribute replaces its value. A multi-valued one adds or removes the value,
 * except that Unknown and Not applicable stand alone (ADR 0011): choosing one of them, or an
 * ordinary value while one of them is held, replaces what is held.
 */
export function pickChange (attribute: Attribute, current: string[], value: AttributeValue, checked: boolean): AssignChange {
  if (!checked) return { mode: AssignMode.remove, valueIds: [value.id] }
  if (attribute.cardinality === Cardinality.single) return { mode: AssignMode.replace, valueIds: [value.id] }
  const holdsSpecial = heldValues(attribute, current).some(h => h.value && isSpecial(h.value))
  return isSpecial(value) || holdsSpecial
    ? { mode: AssignMode.replace, valueIds: [value.id] }
    : { mode: AssignMode.add, valueIds: [value.id] }
}

/** Removing everything the annotation holds of the attribute, without naming the values (`clear`):
 * also values the attribute retired or no longer defines. */
export const clearChange = (): AssignChange => ({ mode: AssignMode.clear, valueIds: [] })

/** The value names of `ids`, quoted and joined, in the attribute's order. */
export function quotedValues (attribute: Attribute, ids: string[]): string {
  const chosen = new Set(ids)
  const names = orderedValues(attribute).filter(v => chosen.has(v.id)).map(v => `"${valueName(v)}"`)
  if (names.length <= 1) return names.join('')
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

// Reasons that read the same for every annotation; the others (`check_value`, `check_cardinality`
// have several) are the server's own words.
const REFUSED: Record<string, string> = {
  check_annotation_type: 'Only confirmed annotations take values.',
  check_applicable: 'The attribute does not apply to their tag.'
}

/** One line of an assignment's result: how many annotations (none for a note) and what. */
export interface ReportLine {
  count: number | null
  label: string
  detail?: string
}

/** What an assignment report says: a headline, then one line per outcome, so each count stands
 * next to its own reason. */
export function assignReportSummary (report: AssignReport, attribute: Attribute | null): { title: string, lines: ReportLine[] } {
  const r = report
  const lines: ReportLine[] = []
  const uncertain = r.failed.filter(f => f.uncertain).length
  if (r.failed.length - uncertain) lines.push({ count: r.failed.length - uncertain, label: 'failed' })
  if (uncertain) lines.push({ count: uncertain, label: 'uncertain', detail: 'The server did not confirm; they may have been saved.' })
  if (r.conflicts.length) {
    lines.push({
      count: r.conflicts.length,
      label: 'not saved',
      detail: 'Changed by someone else since you selected them.'
    })
  }
  const byReason = new Map<string, number>()
  for (const f of r.refused) {
    const reason = REFUSED[f.step] ?? f.message
    byReason.set(reason, (byReason.get(reason) ?? 0) + 1)
  }
  for (const [reason, count] of byReason) lines.push({ count, label: 'not changed', detail: reason })
  if (r.missing.length) {
    lines.push({ count: r.missing.length, label: 'no longer exist', detail: 'Removed from the selection.' })
  }
  if (r.unrecorded.length) {
    lines.push({ count: r.unrecorded.length, label: 'saved without history', detail: 'Their change could not be recorded; the values are saved.' })
  }
  if (r.error) lines.push({ count: null, label: r.error })
  if (r.saved.length && (r.failed.length || r.conflicts.length)) lines.push({ count: null, label: 'Saved changes are kept.' })
  const name = attribute ? `"${attribute.name}": ` : ''
  return { title: `${name}saved ${r.saved.length} of ${plural(r.target, 'annotation')}`, lines }
}

/** Whether the report has anything besides saved changes. */
export const assignReportHasProblems = (r: AssignReport) =>
  r.failed.length > 0 || r.conflicts.length > 0 || r.refused.length > 0 || r.missing.length > 0 ||
  r.unrecorded.length > 0 || !!r.error
