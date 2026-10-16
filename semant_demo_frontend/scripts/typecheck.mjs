#!/usr/bin/env node
// Vue-aware type check gated by a baseline of known legacy errors.
//
// The check fails when vue-tsc reports an error that is not in the baseline, or when a
// baseline error no longer occurs (remove fixed entries with `--update`). Entries are keyed
// by file, error code and message, not line number, so unrelated edits do not shift them.
// The baseline only shrinks: do not add new errors to it to make the check pass.
//
// Usage: node scripts/typecheck.mjs [--update]
import { spawnSync } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const baselinePath = join(root, 'typecheck-baseline.json')
const update = process.argv.includes('--update')

const result = spawnSync(
  process.execPath,
  [join(root, 'node_modules/vue-tsc/bin/vue-tsc.js'), '--noEmit', '--pretty', 'false', '-p', 'tsconfig.json'],
  { cwd: root, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 }
)
const output = `${result.stdout}${result.stderr}`
const errorLine = /^(.+?)\(\d+,\d+\): error (TS\d+): (.*)$/

// TypeScript truncates long inline object types differently between runs; keep the message
// up to the first inline object type so the key is stable.
function normalize (message) {
  const inlineType = message.indexOf("'{")
  return inlineType === -1 ? message : `${message.slice(0, inlineType)}'{…}'`
}

const current = {}
for (const line of output.split('\n')) {
  const match = errorLine.exec(line)
  if (match) {
    const key = `${match[1]}: ${match[2]}: ${normalize(match[3])}`
    current[key] = (current[key] ?? 0) + 1
  }
}
const errorCount = Object.values(current).reduce((sum, n) => sum + n, 0)

// A crashed compiler prints no diagnostics; never treat that as a pass.
if (result.status !== 0 && errorCount === 0) {
  process.stderr.write(output)
  console.error(`vue-tsc failed without reporting type errors (exit ${result.status ?? result.signal}).`)
  process.exit(1)
}

const baseline = JSON.parse(readFileSync(baselinePath, 'utf8'))

if (update) {
  const shrunk = {}
  const added = []
  for (const [key, count] of Object.entries(current)) {
    const known = baseline[key] ?? 0
    if (count > known) added.push(key)
    if (Math.min(count, known) > 0) shrunk[key] = Math.min(count, known)
  }
  const sorted = Object.fromEntries(Object.entries(shrunk).sort(([a], [b]) => a.localeCompare(b)))
  writeFileSync(baselinePath, `${JSON.stringify(sorted, null, 2)}\n`)
  console.log(`Baseline updated: ${Object.values(sorted).reduce((s, n) => s + n, 0)} known errors.`)
  if (added.length) {
    console.error('New errors were NOT added to the baseline; fix them:')
    for (const key of added) console.error(`  ${key}`)
    process.exit(1)
  }
  process.exit(0)
}

const newErrors = []
const fixed = []
for (const key of new Set([...Object.keys(current), ...Object.keys(baseline)])) {
  const count = current[key] ?? 0
  const known = baseline[key] ?? 0
  if (count > known) newErrors.push(`${key} (${count} found, ${known} known)`)
  if (count < known) fixed.push(`${key} (${count} found, ${known} known)`)
}

if (newErrors.length) {
  console.error('New type errors:')
  for (const key of newErrors) console.error(`  ${key}`)
  console.error('\nFull vue-tsc output:')
  process.stderr.write(output)
}
if (fixed.length) {
  console.error('Baseline errors no longer reported; run `npm run typecheck -- --update` to remove them:')
  for (const key of fixed) console.error(`  ${key}`)
}
if (newErrors.length || fixed.length) process.exit(1)

console.log(`Type check passed (${errorCount} known legacy errors in typecheck-baseline.json).`)
