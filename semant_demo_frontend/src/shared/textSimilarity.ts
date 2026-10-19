/** Classic Levenshtein edit distance. Cheap for short strings; avoid it on long documents. */
export function levenshtein(a: string, b: string): number {
  if (a === b) return 0
  const m = a.length
  const n = b.length
  if (m === 0) return n
  if (n === 0) return m

  let prev = Array.from({ length: n + 1 }, (_, j) => j)
  const curr = new Array(n + 1).fill(0)
  for (let i = 1; i <= m; i++) {
    curr[0] = i
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1
      curr[j] = Math.min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
    }
    prev = [...curr]
  }
  return prev[n]
}

/** 0 (nothing alike) .. 1 (identical), case/whitespace-insensitive. */
export function similarity(a: string, b: string): number {
  const x = a.trim().toLowerCase()
  const y = b.trim().toLowerCase()
  if (!x || !y) return 0
  return 1 - levenshtein(x, y) / Math.max(x.length, y.length)
}
