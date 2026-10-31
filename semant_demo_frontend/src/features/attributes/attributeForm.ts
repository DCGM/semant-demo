import {
  ValueKind, type Attribute, type AttributeValue, type PatchAttributeValue, type PostAttributeValue, type Tag
} from 'src/generated/api'

/** Limits of the backend (`features/attributes/schemas.py`). */
export const MAX_NAME = 200
export const MAX_DESCRIPTION = 2000
export const MAX_EXAMPLES = 20
export const MAX_VALUES = 200

/** A description field of modest height that scrolls inside, so a long text never pushes the
 * rest of the form away (#506); it can be pulled taller up to a limit. */
export const DESCRIPTION_STYLE = { height: '7.5em', maxHeight: '20em', resize: 'vertical' }

export const KIND_LABELS: Record<ValueKind, string> = {
  [ValueKind.value]: 'Value',
  [ValueKind.unknown]: 'Unknown',
  [ValueKind.notApplicable]: 'Not applicable'
}

/** The fixed special values an attribute may allow, at most one of each (ADR 0011). They are
 * explicit decisions, distinct from no value, and are shown by their kind, never by a label. */
export type SpecialKind = typeof ValueKind.unknown | typeof ValueKind.notApplicable
export const SPECIAL_KINDS: SpecialKind[] = [ValueKind.unknown, ValueKind.notApplicable]

export const isSpecial = (value: Pick<AttributeValue, 'kind'>) => (value.kind ?? ValueKind.value) !== ValueKind.value

/** What a value is called: its label, or the name of its special kind. */
export const valueName = (value: Pick<AttributeValue, 'kind' | 'label'>) =>
  isSpecial(value) ? KIND_LABELS[value.kind!] : value.label

/** The value writes of the attribute an Edit dialog shows, each answering with the whole
 * attribute as saved. */
export type ValueActions = {
  addValue: (value: PostAttributeValue) => Promise<Attribute>
  updateValue: (valueId: string, patch: PatchAttributeValue) => Promise<Attribute>
  setSpecialValue: (attribute: Attribute, kind: SpecialKind, allowed: boolean) => Promise<Attribute>
}

/** The attribute's value of a special kind, retired or not. */
export const specialValue = (attribute: Pick<Attribute, 'values'>, kind: SpecialKind) =>
  (attribute.values ?? []).find(v => v.kind === kind)

/** Whether the attribute offers a special kind now (it has one that is not retired). */
export function allows (attribute: Pick<Attribute, 'values'>, kind: SpecialKind): boolean {
  const value = specialValue(attribute, kind)
  return !!value && !value.retired
}

/** The attribute's ordinary values first, then its special ones, each in stored order. */
export const orderedValues = (attribute: Pick<Attribute, 'values'>): AttributeValue[] => {
  const values = attribute.values ?? []
  return [...values.filter(v => !isSpecial(v)), ...values.filter(isSpecial)]
}

/** Names of the tags an attribute selects, in the collection's order; ids of tags no longer
 * in the collection are left out. An All tags attribute (`allTags`) selects none. */
export function tagNames (attribute: Pick<Attribute, 'tagIds'>, tags: Tag[]): string[] {
  const ids = new Set(attribute.tagIds ?? [])
  return tags.filter(tag => ids.has(tag.id)).map(tag => tag.name)
}

/** Whether the collection's tags are known yet. */
export type TagsState = 'loading' | 'failed' | 'ready'

/** What is known about the tags an attribute applies to. All tags is explicit (`allTags`); with
 * selected tags, an empty list is no tag at all (#522). Ids of deleted tags (their ids stay on the
 * attribute, #508) are counted, not named; while the tags are unknown, the selected ones cannot
 * be named. */
export type TagScope =
  | { kind: 'all' }
  | { kind: 'none' }
  | { kind: 'loading' }
  | { kind: 'failed' }
  | { kind: 'selected', names: string[], deleted: number }

export function tagScope (attribute: Pick<Attribute, 'allTags' | 'tagIds'>, tags: Tag[], state: TagsState): TagScope {
  if (attribute.allTags) return { kind: 'all' }
  if (!attribute.tagIds?.length) return { kind: 'none' }
  if (state !== 'ready') return { kind: state }
  const names = tagNames(attribute, tags)
  return { kind: 'selected', names, deleted: attribute.tagIds.length - names.length }
}

/** The attributes that apply to a tag and are not retired: those that name it first, then those
 * for all tags (`allTags`), each by name as listed. */
export function attributesOfTag (attributes: Attribute[], tagId: string): { attribute: Attribute, allTags: boolean }[] {
  const current = attributes.filter(a => !a.retired)
  return [
    ...current.filter(a => !a.allTags && a.tagIds?.includes(tagId)).map(attribute => ({ attribute, allTags: false })),
    ...current.filter(a => a.allTags).map(attribute => ({ attribute, allTags: true }))
  ]
}

/** How the backend compares attribute names and value labels: unique ignoring case and
 * surrounding spaces (ADR 0011). */
export const nameKey = (text: string) => text.trim().toLocaleLowerCase()

/** Why `name` cannot name a new or renamed attribute, or null: another attribute of the
 * collection, retired ones included, has it. */
export function nameTaken (name: string, others: Pick<Attribute, 'name' | 'retired'>[]): string | null {
  const key = nameKey(name)
  const other = key ? others.find(a => nameKey(a.name) === key) : undefined
  if (!other) return null
  return other.retired
    ? `A retired attribute is already named "${other.name}"; restore it, or choose another name.`
    : `An attribute named "${other.name}" already exists in this collection.`
}

/** Why `label` cannot label a value of the attribute, or null: another of its values, retired
 * ones included, has it. */
export function labelTaken (label: string, others: Pick<AttributeValue, 'label' | 'kind' | 'retired'>[]): string | null {
  const key = nameKey(label)
  const other = key ? others.find(v => nameKey(v.label) === key) : undefined
  if (!other) return null
  if (isSpecial(other)) return `"${valueName(other)}" is a fixed option of the attribute; use its toggle.`
  return other.retired
    ? `A retired value is already labelled "${other.label}"; restore it, or choose another label.`
    : `Another value is already labelled "${other.label}".`
}

/** Text entries trimmed, without empty ones. */
export function cleanList (items: string[]): string[] {
  return items.map(item => item.trim()).filter(item => item.length > 0)
}
