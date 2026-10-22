/** "1 tag", "2 tags": a count with the noun in the matching form. */
export function plural (n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`
}
