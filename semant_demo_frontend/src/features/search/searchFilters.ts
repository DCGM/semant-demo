import type { SearchFilter } from 'src/generated/api'

/** Range of an interval filter's slider, from the bounds the server reports. */
export interface IntervalValue {
  min: number
  max: number
}

/** `publication_year` -> `Publication Year`: the label of a search filter. */
export function formatFilterLabel (id: string): string {
  return id
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

/** Range of an interval filter (the generated client types its numeric bounds loosely). */
export function intervalBounds (filter: SearchFilter): IntervalValue {
  const min = filter.minValue != null ? Math.floor(Number(filter.minValue)) : 1800
  const max = filter.maxValue != null ? Math.ceil(Number(filter.maxValue)) : 2026
  return { min, max }
}

/** Shown label of a nominal filter value; the value itself when the filter does not list it. */
export function nominalLabel (filter: SearchFilter | undefined, value: string): string {
  return filter?.values?.find(v => v.backendForm === value || v.userForm === value)?.userForm ?? value
}
