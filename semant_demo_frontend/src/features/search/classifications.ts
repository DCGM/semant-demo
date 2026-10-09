import type { SearchFilter } from 'src/generated/api'

/** Badge background and text color (Quasar palette names, e.g. `teal-4`, `teal-10`). */
export interface BadgeColor {
  bg: string
  text: string
}

/** One classification value of a search hit, shown as a badge colored by its category. */
export interface ClassificationBadge {
  key: string
  category: string
  value: string
  color: BadgeColor
}

const HUES = ['blue', 'green', 'orange', 'purple', 'red', 'teal', 'brown', 'pink', 'grey']

/**
 * Category colors: distinct hues in a pale and then a stronger tone, so similar hues
 * (orange/amber, blue/cyan) are never both used. More than the configured search filters.
 */
export const CATEGORY_COLORS: BadgeColor[] = [
  ...HUES.map(hue => ({ bg: `${hue}-${hue === 'grey' ? 3 : 1}`, text: `${hue}-9` })),
  ...HUES.map(hue => ({ bg: `${hue}-${hue === 'grey' ? 5 : 4}`, text: `${hue}-10` }))
]

/** `subject_domain` -> `Subject Domain`: fallback for names no filter defines. */
export function humanizeName (name: string): string {
  return name
    .split('_')
    .filter(Boolean)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

/**
 * Color of a classification category: by the position of its search filter, so every
 * configured category has its own color on every result; unknown categories by a hash.
 */
export function categoryColor (key: string, filters: readonly SearchFilter[]): BadgeColor {
  const index = filters.findIndex(f => f.targetProperty === key)
  if (index >= 0) return CATEGORY_COLORS[index % CATEGORY_COLORS.length]
  let hash = 0
  for (const ch of key) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  return CATEGORY_COLORS[hash % CATEGORY_COLORS.length]
}

/**
 * The values of a hit's populated classifications (`metadata`), in the order the backend
 * returns them, named by the search filter that targets each property (`name`,
 * `user_form`) with a humanized fallback.
 */
export function classificationBadges (
  metadata: Record<string, string[]> | null | undefined,
  filters: readonly SearchFilter[]
): ClassificationBadge[] {
  if (!metadata) return []
  return Object.entries(metadata).flatMap(([key, values]) => {
    const filter = filters.find(f => f.targetProperty === key)
    const category = filter?.name || humanizeName(key)
    const color = categoryColor(key, filters)
    return (values ?? []).map(value => ({
      key: `${key}:${value}`,
      category,
      value: filter?.values?.find(v => v.backendForm === value)?.userForm || humanizeName(value),
      color
    }))
  })
}
