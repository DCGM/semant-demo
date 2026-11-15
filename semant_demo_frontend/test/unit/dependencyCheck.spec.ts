// @vitest-environment node
// The frontend dependency preflight, scripts/check-deps.mjs (#673): node_modules must hold
// what package-lock.json locks, as recorded by npm in node_modules/.package-lock.json.
import { spawnSync } from 'child_process'
import { copyFileSync, mkdirSync, mkdtempSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join, resolve } from 'path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

const frontend = resolve(__dirname, '../..')

const lock = (packages: Record<string, object>) =>
  JSON.stringify({ lockfileVersion: 3, packages: { '': { name: 'probe' }, ...packages } })

describe('scripts/check-deps.mjs', () => {
  let dir: string
  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), 'check-deps-'))
    mkdirSync(join(dir, 'scripts'))
    copyFileSync(join(frontend, 'scripts/check-deps.mjs'), join(dir, 'scripts/check-deps.mjs'))
    writeFileSync(join(dir, 'package-lock.json'), lock({
      'node_modules/vue': { version: '3.5.0' },
      'node_modules/@tanstack/vue-query': { version: '5.104.5', dev: true },
      'node_modules/esbuild-darwin-64': { version: '0.14.0', optional: true, os: ['darwin'] },
      'node_modules/local': { resolved: '../local', link: true }
    }))
  })
  afterEach(() => { spawnSync('rm', ['-rf', dir]) })

  const installed = (packages: Record<string, object>) => {
    mkdirSync(join(dir, 'node_modules'), { recursive: true })
    writeFileSync(join(dir, 'node_modules/.package-lock.json'), lock(packages))
  }
  const check = () => spawnSync(process.execPath, [join(dir, 'scripts/check-deps.mjs')], { encoding: 'utf8' })

  it('refuses a checkout without an npm-installed node_modules', () => {
    mkdirSync(join(dir, 'node_modules'))

    const result = check()

    expect(result.status).toBe(1)
    expect(result.stderr).toContain('no node_modules/.package-lock.json')
    expect(result.stderr).toContain('npm ci')
  })

  it('names packages missing or at another version after a lock change', () => {
    installed({ 'node_modules/vue': { version: '3.4.0' } })

    const result = check()

    expect(result.status).toBe(1)
    expect(result.stderr).toContain('node_modules/vue is 3.4.0, locked 3.5.0')
    expect(result.stderr).toContain('node_modules/@tanstack/vue-query@5.104.5 is missing')
    expect(result.stderr).not.toContain('esbuild-darwin-64')
  })

  it('passes quietly once node_modules matches the lock, skipping optional platform builds', () => {
    installed({ 'node_modules/vue': { version: '3.5.0' }, 'node_modules/@tanstack/vue-query': { version: '5.104.5' } })

    const result = check()

    expect([result.status, result.stdout, result.stderr]).toEqual([0, '', ''])
  })
})
