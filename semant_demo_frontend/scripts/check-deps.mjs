#!/usr/bin/env node
// Fail fast when node_modules does not match package-lock.json (#673).
//
// `npm ci` / `npm install` record what they installed in node_modules/.package-lock.json.
// Every package of package-lock.json must be there with the same version, except native
// builds whose os/cpu/libc exclude this platform (npm skips those). Nothing is resolved
// or installed.
//
// Usage: node scripts/check-deps.mjs
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')

// npm's `os` / `cpu` / `libc` lists: names, or `!name` exclusions; absent means any.
function allows(list, value) {
  if (!list?.length) return true
  if (list.includes(`!${value}`)) return false
  const wanted = list.filter((name) => !name.startsWith('!'))
  return wanted.length === 0 || wanted.includes(value)
}

let libc = null
function currentLibc() {
  if (libc === null) {
    libc = process.platform !== 'linux' ? undefined
      : process.report?.getReport().header.glibcVersionRuntime ? 'glibc' : 'musl'
  }
  return libc
}

// A native build for another platform, which npm skips (e.g. esbuild-darwin-64 on Linux);
// the current platform's build (esbuild-linux-64 on Linux x64) is required although optional.
function forAnotherPlatform(entry) {
  return !allows(entry.os, process.platform) || !allows(entry.cpu, process.arch) ||
    (entry.libc !== undefined && currentLibc() !== undefined && !allows(entry.libc, currentLibc()))
}

export function lockProblems(locked, installed) {
  const found = []
  for (const [path, entry] of Object.entries(locked.packages ?? {})) {
    if (path === '' || entry.link) continue
    const have = installed.packages?.[path]
    if (!have) {
      if (!forAnotherPlatform(entry)) found.push(`${path}@${entry.version} is missing`)
    } else if (have.version !== entry.version) {
      found.push(`${path} is ${have.version}, locked ${entry.version}`)
    }
  }
  return found
}

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, 'utf8'))
  } catch (error) {
    if (error.code === 'ENOENT') return null
    throw error
  }
}

function main() {
  const locked = readJson(join(root, 'package-lock.json'))
  const installed = readJson(join(root, 'node_modules', '.package-lock.json'))
  const found = installed
    ? lockProblems(locked, installed)
    : ['node_modules is missing or was not installed by npm (no node_modules/.package-lock.json)']
  if (found.length === 0) return 0
  console.error(`Frontend dependencies in ${join(root, 'node_modules')} do not match package-lock.json:`)
  for (const line of found.slice(0, 10)) console.error(`  - ${line}`)
  if (found.length > 10) console.error(`  ... and ${found.length - 10} more`)
  console.error('Repair: (cd semant_demo_frontend && npm ci), or make setup')
  return 1
}

if (process.argv[1] === fileURLToPath(import.meta.url)) process.exit(main())
