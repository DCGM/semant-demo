// @vitest-environment node
// Developer tooling defaults (#275): ESLint's 'no-undef' split between JavaScript and
// TypeScript, and how scripts/api-client.sh picks its backend Python interpreter.
import { spawnSync } from 'child_process'
import { chmodSync, copyFileSync, existsSync, mkdirSync, mkdtempSync, symlinkSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join, resolve } from 'path'
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'

const frontend = resolve(__dirname, '../..')
const which = (tool: string) => spawnSync('bash', ['-c', `command -v ${tool}`], { encoding: 'utf8' }).stdout.trim()

describe('ESLint no-undef', () => {
  // One in-process ESLint with the project's config: the same rules as `npm run lint`,
  // without starting a Node process per case.
  type Message = { ruleId: string | null, message: string }
  type Linter = { lintText (code: string, options: { filePath: string }): Promise<{ messages: Message[] }[]> }
  let eslint: Linter
  beforeAll(async () => {
    const { ESLint } = await import(join(frontend, 'node_modules/eslint/lib/api.js')) as
      { ESLint: new (options: { cwd: string }) => Linter }
    eslint = new ESLint({ cwd: frontend })
  })

  /** Rule ids and messages from linting `code` as `filePath`. */
  async function lint (filePath: string, code: string): Promise<Message[]> {
    const [file] = await eslint.lintText(code, { filePath: join(frontend, filePath) })
    return file.messages
  }
  const undefinedNames = async (filePath: string, code: string) =>
    (await lint(filePath, code)).filter(m => m.ruleId === 'no-undef').map(m => m.message)

  it('ignores TypeScript type names in .ts files and Vue TypeScript scripts', async () => {
    expect(await undefinedNames('src/probe.ts',
      "export const init: KeyboardEventInit = { key: 'a' }\n")).toEqual([])
    expect(await undefinedNames('src/components/ProbeComponent.vue',
      "<script setup lang=\"ts\">\nconst init: KeyboardEventInit = { key: 'a' }\nconsole.log(init)\n</script>\n\n<template><div /></template>\n"
    )).toEqual([])
  }, 30_000)

  it('still reports an undefined runtime variable in JavaScript', async () => {
    expect(await undefinedNames('src/probe.js', 'module.exports = undefinedThing\n'))
      .toEqual(["'undefinedThing' is not defined."])
  }, 30_000)

  it('requires TypeScript component scripts, which the type check covers', async () => {
    const messages = await lint('src/components/ProbeComponent.vue', '<script setup>\nconsole.log(1)\n</script>\n\n<template><div /></template>\n')
    expect(messages.map(m => m.ruleId)).toContain('vue/block-lang')
  }, 30_000)
})

describe('api-client.sh interpreter', () => {
  // A copy of the script in a fake checkout, so the repository's own .venv is not found.
  let repo: string
  let script: string

  beforeEach(() => {
    repo = mkdtempSync(join(tmpdir(), 'api-client-'))
    mkdirSync(join(repo, 'semant_demo_frontend/scripts'), { recursive: true })
    mkdirSync(join(repo, 'semant_demo_backend'))
    script = join(repo, 'semant_demo_frontend/scripts/api-client.sh')
    copyFileSync(join(frontend, 'scripts/api-client.sh'), script)
  })
  afterEach(() => { spawnSync('rm', ['-rf', repo]) })

  /** Run the script from `cwd` (not the frontend directory) with extra environment. */
  function run (env: Record<string, string>, cwd = repo) {
    const inherited = { ...process.env }
    delete inherited.PYTHON
    delete inherited.OPENAPI_JSON
    delete inherited.OPENAPI_GENERATOR
    return spawnSync(which('bash'), [script, 'check'], { cwd, env: { ...inherited, ...env }, encoding: 'utf8' })
  }

  /** An executable that records its arguments and fails like a Python without the backend. */
  function fakePython (path: string) {
    writeFileSync(path, '#!/bin/sh\necho "$@" > "$(dirname "$0")/called"\nexit 3\n')
    chmodSync(path, 0o755)
  }

  it('fails with setup instructions when the repository .venv is missing', () => {
    const result = run({ OPENAPI_GENERATOR: 'true' })
    expect(result.status).toBe(1)
    expect(result.stderr).toContain(`${repo}/.venv/bin/python is missing or broken`)
    expect(result.stderr).toContain("'make setup'")
  })

  it('uses the repository .venv by default from any directory', () => {
    mkdirSync(join(repo, '.venv/bin'), { recursive: true })
    fakePython(join(repo, '.venv/bin/python'))
    const result = run({ OPENAPI_GENERATOR: 'true' }, join(repo, 'semant_demo_backend'))
    expect(result.status).toBe(1)
    expect(existsSync(join(repo, '.venv/bin/called'))).toBe(true)
    expect(result.stderr).toContain('Exporting the OpenAPI schema with')
  })

  it('honors PYTHON, resolving a relative path against the caller directory', () => {
    mkdirSync(join(repo, 'other'))
    fakePython(join(repo, 'other/python'))
    const result = run({ PYTHON: 'other/python', OPENAPI_GENERATOR: 'true' })
    expect(result.status).toBe(1)
    expect(existsSync(join(repo, 'other/called'))).toBe(true)
  })

  it('reports a PYTHON that does not exist instead of running another interpreter', () => {
    const result = run({ PYTHON: join(repo, 'missing/python'), OPENAPI_GENERATOR: 'true' })
    expect(result.status).toBe(1)
    expect(result.stderr).toContain('is not an executable or a command on PATH')
  })

  it('reports missing Java for the default generator', () => {
    // A PATH with only the tools the script needs before its Java check.
    const bin = join(repo, 'bin')
    mkdirSync(bin)
    symlinkSync(which('dirname'), join(bin, 'dirname'))
    fakePython(join(repo, 'python'))
    const result = run({ PYTHON: join(repo, 'python'), PATH: bin })
    expect(result.status).toBe(1)
    expect(result.stderr).toContain('needs Java 11+')
  })
})
