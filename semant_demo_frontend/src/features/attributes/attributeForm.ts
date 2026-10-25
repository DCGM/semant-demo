import { ValueKind, type Attribute, type Tag } from 'src/generated/api'

/** Limits of the backend (`features/attributes/schemas.py`). */
export const MAX_NAME = 200
export const MAX_DESCRIPTION = 2000
export const MAX_EXAMPLES = 20
export const MAX_VALUES = 200

export const KIND_LABELS: Record<ValueKind, string> = {
  [ValueKind.value]: 'Value',
  [ValueKind.unknown]: 'Unknown',
  [ValueKind.notApplicable]: 'Not applicable'
}

export const kindOptions = Object.values(ValueKind).map(kind => ({ label: KIND_LABELS[kind], value: kind }))

/** The special kinds (Unknown, Not applicable) that occur more than once; an attribute has at
 * most one value of each. */
export function repeatedKinds (kinds: ValueKind[]): ValueKind[] {
  return [ValueKind.unknown, ValueKind.notApplicable].filter(kind => kinds.filter(k => k === kind).length > 1)
}

/** Names of the tags an attribute applies to, in the collection's order; ids of tags no longer
 * in the collection are left out. Empty: every tag. */
export function tagNames (attribute: Pick<Attribute, 'tagIds'>, tags: Tag[]): string[] {
  const ids = new Set(attribute.tagIds ?? [])
  return tags.filter(tag => ids.has(tag.id)).map(tag => tag.name)
}

/** What a card says about the tags an attribute applies to. Ids of deleted tags (their ids
 * stay on the attribute, #508) are not named; an attribute left with only those applies to no
 * existing tag. */
export function appliesTo (attribute: Pick<Attribute, 'tagIds'>, tags: Tag[]): string {
  if (!attribute.tagIds?.length) return 'all tags'
  const names = tagNames(attribute, tags)
  return names.length ? `tags ${names.join(', ')}` : 'only deleted tags'
}

/** Text entries trimmed, without empty ones. */
export function cleanList (items: string[]): string[] {
  return items.map(item => item.trim()).filter(item => item.length > 0)
}
