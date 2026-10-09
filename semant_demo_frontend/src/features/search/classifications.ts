import type { SearchFilter } from 'src/generated/api'

/** One classification of a search hit, ready to show: "label: values". */
export interface ClassificationRow {
  key: string
  label: string
  values: string[]
}

/** `subject_domain` -> `Subject Domain`: fallback for names no filter defines. */
export function humanizeName (name: string): string {
  return name
    .split('_')
    .filter(Boolean)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

/**
 * The populated classifications of a hit (`metadata`) with the names and values of the
 * search filter that targets each property. Keeps the order the backend returns;
 * unknown properties and values get a humanized fallback.
 */
export function classificationRows (
  metadata: Record<string, string[]> | null | undefined,
  filters: readonly SearchFilter[]
): ClassificationRow[] {
  if (!metadata) return []
  const byProperty = new Map(filters.map(f => [f.targetProperty, f]))
  return Object.entries(metadata)
    .filter(([, values]) => values?.length)
    .map(([key, values]) => {
      const filter = byProperty.get(key)
      return {
        key,
        label: filter?.name || humanizeName(key),
        values: values.map(value =>
          filter?.values?.find(v => v.backendForm === value)?.userForm || humanizeName(value))
      }
    })
}
