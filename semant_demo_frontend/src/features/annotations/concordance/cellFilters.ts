import { SpanType, TextScope, type AnnotationListRow, type Attribute } from 'src/generated/api'
import { heldName, heldValues } from 'src/features/attributes/assignment'
import { defaultFilters, type ConcordanceFilters } from './concordanceStore'
import { SCOPE_LABELS, scopeHintText } from './filterChips'
import { queryWords } from './textMatches'

/**
 * The filters a concordance row offers from its displayed values (#665): *Only this* and *Clear*
 * for its source, year, tag and shown attribute values, also *Exclude this* for its status (the
 * statuses are a set of included values, so excluding one is removing it), and a filter by the
 * words selected in its text. Each one is a change of the query; it composes with the other
 * filters and shows as their chip, whose removal undoes it.
 */

export interface CellFilterAction {
  /** Unique within the row's menu. */
  key: string
  label: string
  icon: string
  change: Partial<ConcordanceFilters>
}

export interface CellFilterGroup {
  key: string
  /** The field and the row's value of it, e.g. "Source · Kronika obce Lhota". */
  label: string
  /** What the actions do, where it needs saying (the word filter's matching rules). */
  caption?: string
  actions: CellFilterAction[]
}

const ONLY = 'filter_alt'
const EXCLUDE = 'block'
const CLEAR = 'filter_alt_off'

const STATUS_NAMES: Record<SpanType, string> = {
  [SpanType.pos]: 'Confirmed',
  [SpanType.auto]: 'Proposal',
  [SpanType.neg]: 'Rejected'
}

const sameSet = (a: readonly string[], b: readonly string[]) =>
  a.length === b.length && a.every(v => b.includes(v))

function sourceGroup (row: AnnotationListRow, f: ConcordanceFilters): CellFilterGroup | null {
  if (!row.documentAvailable || !row.documentId) return null
  const id = row.documentId
  const actions: CellFilterAction[] = []
  if (!sameSet(f.documentIds, [id])) actions.push({ key: 'source-only', label: 'Only this source', icon: ONLY, change: { documentIds: [id] } })
  if (f.documentIds.length) actions.push({ key: 'source-clear', label: 'Clear the source filter', icon: CLEAR, change: { documentIds: [] } })
  return { key: 'source', label: `Source · ${row.documentTitle || 'Untitled document'}`, actions }
}

function yearGroup (row: AnnotationListRow, f: ConcordanceFilters): CellFilterGroup | null {
  const year = row.documentAvailable ? row.documentYear : null
  if (year == null) return null
  const { yearMin, yearMax, ...others } = f.documentFilters
  const actions: CellFilterAction[] = []
  if (yearMin !== year || yearMax !== year) {
    actions.push({ key: 'year-only', label: 'Only this year', icon: ONLY, change: { documentFilters: { ...others, yearMin: year, yearMax: year } } })
  }
  if (yearMin != null || yearMax != null) {
    actions.push({ key: 'year-clear', label: 'Clear the year filter', icon: CLEAR, change: { documentFilters: others } })
  }
  return { key: 'year', label: `Year · ${year}`, actions }
}

function tagGroup (row: AnnotationListRow, f: ConcordanceFilters, tagName: string): CellFilterGroup | null {
  if (!row.tagId) return null
  const actions: CellFilterAction[] = []
  if (!sameSet(f.tagIds, [row.tagId])) actions.push({ key: 'tag-only', label: 'Only this tag', icon: ONLY, change: { tagIds: [row.tagId] } })
  if (f.tagIds.length) actions.push({ key: 'tag-clear', label: 'Clear the tag filter', icon: CLEAR, change: { tagIds: [] } })
  return { key: 'tag', label: `Tag · ${tagName}`, actions }
}

function statusGroup (row: AnnotationListRow, f: ConcordanceFilters): CellFilterGroup | null {
  const type = row.type
  if (!type) return null
  const defaults = defaultFilters().types
  const actions: CellFilterAction[] = []
  if (!sameSet(f.types, [type])) actions.push({ key: 'status-only', label: 'Only this status', icon: ONLY, change: { types: [type] } })
  // At least one status stays: the server needs one.
  if (f.types.includes(type) && f.types.length > 1) {
    actions.push({ key: 'status-exclude', label: 'Exclude this status', icon: EXCLUDE, change: { types: f.types.filter(t => t !== type) } })
  }
  if (!sameSet(f.types, defaults)) actions.push({ key: 'status-clear', label: 'Reset the status filter', icon: CLEAR, change: { types: defaults } })
  return { key: 'status', label: `Status · ${STATUS_NAMES[type]}`, actions }
}

/** A shown attribute: *Only* each held value (it replaces the attribute's other accepted values,
 * as values of one attribute match any), or *Only not assigned* for a row without one. */
function attributeGroup (row: AnnotationListRow, f: ConcordanceFilters, attribute: Attribute): CellFilterGroup {
  const prefix = `${attribute.id}:`
  const values = f.attributeValues.filter(v => !v.startsWith(prefix))
  const unassigned = f.attributeUnassigned.filter(a => a !== attribute.id)
  const ownValues = f.attributeValues.filter(v => v.startsWith(prefix))
  const held = heldValues(attribute, row.attributes?.[attribute.id])
  const actions: CellFilterAction[] = []
  if (held.length) {
    for (const value of held) {
      if (sameSet(ownValues, [`${prefix}${value.id}`]) && !f.attributeUnassigned.includes(attribute.id)) continue
      actions.push({
        key: `attribute-only-${attribute.id}-${value.id}`,
        label: held.length > 1 ? `Only ${heldName(value)}` : 'Only this value',
        icon: ONLY,
        change: { attributeValues: [...values, `${prefix}${value.id}`], attributeUnassigned: unassigned }
      })
    }
  } else if (ownValues.length || !f.attributeUnassigned.includes(attribute.id)) {
    actions.push({
      key: `attribute-unassigned-${attribute.id}`,
      label: 'Only not assigned',
      icon: ONLY,
      change: { attributeValues: values, attributeUnassigned: [...unassigned, attribute.id] }
    })
  }
  if (ownValues.length || f.attributeUnassigned.includes(attribute.id)) {
    actions.push({
      key: `attribute-clear-${attribute.id}`,
      label: `Clear the ${attribute.name} filter`,
      icon: CLEAR,
      change: { attributeValues: values, attributeUnassigned: unassigned }
    })
  }
  const shown = held.length ? held.map(heldName).join(', ') : 'not assigned'
  return { key: `attribute-${attribute.id}`, label: `${attribute.name} · ${shown}`, actions }
}

/** The value filters of a row, in the order of its cells: shown attributes, tag, status, source, year.
 * Groups without an action are left out. */
export function rowFilterGroups (row: AnnotationListRow, f: ConcordanceFilters,
  context: { tagName: string, attributes: Attribute[] }): CellFilterGroup[] {
  const groups = [
    ...context.attributes.map(a => attributeGroup(row, f, a)),
    tagGroup(row, f, context.tagName),
    statusGroup(row, f),
    sourceGroup(row, f),
    yearGroup(row, f)
  ]
  return groups.filter((g): g is CellFilterGroup => !!g && g.actions.length > 0)
}

/** The longest text filter the server takes (`MAX_QUERY_TEXT_LENGTH`) and the words it uses. */
const MAX_TEXT = 500
const MAX_WORDS = 10

const WORD_LABELS: Record<TextScope, (quoted: string) => string> = {
  [TextScope.annotation]: quoted => `Filter annotations containing ${quoted}`,
  [TextScope.context]: quoted => `Filter annotations with ${quoted} in their context`,
  [TextScope.both]: quoted => `Filter annotations with ${quoted} in them or their context`
}

/**
 * The filter by the words of `selected` (text selected in a row), in `scope`, the field(s) it was
 * selected in: they are added to the text filter of the same scope; a text filter of another scope
 * (or one that would grow too long) is replaced, which the caption says. None without a word.
 */
export function wordFilterGroup (selected: string, scope: TextScope, f: ConcordanceFilters): CellFilterGroup | null {
  const words = [...new Set(queryWords(selected))]
  if (!words.length) return null
  const current = f.text.trim()
  const currentWords = queryWords(current)
  const lower = new Set(currentWords.map(w => w.toLocaleLowerCase()))
  const added = words.filter(w => !lower.has(w.toLocaleLowerCase()))
  const joined = added.length ? `${current} ${added.join(' ')}` : current
  const appends = !!current && f.textScope === scope && currentWords.length + added.length <= MAX_WORDS && joined.length <= MAX_TEXT
  const text = appends ? joined : words.join(' ').slice(0, MAX_TEXT)
  if (appends && !added.length) return null // every word is filtered already
  const quoted = `“${words.join(' ')}”`
  const where = SCOPE_LABELS[scope].toLowerCase()
  const caption = [
    scopeHintText(scope),
    current && !appends ? `Replaces the text filter “${current}”.` : ''
  ].filter(Boolean).join(' ')
  return {
    key: 'words',
    label: `Selected text · ${where}`,
    caption,
    actions: [{
      key: 'words',
      label: WORD_LABELS[scope](quoted),
      icon: ONLY,
      change: { text, textScope: scope }
    }]
  }
}
