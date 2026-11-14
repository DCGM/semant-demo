// @vitest-environment node
// The timer tracking of the unit-test environment (#551, `environment/timers.js`): it must
// behave like Node's timer functions while a file runs and end everything with the file.
import { promisify } from 'util'
import { describe, expect, it } from 'vitest'
import { trackTimers } from './environment/timers.js'

type Timers = Pick<typeof globalThis, 'setTimeout' | 'clearTimeout' | 'setInterval' | 'clearInterval'>

// A stand-in for the global object, so the run's own timer functions stay untouched.
function install () {
  const original: Timers = { setTimeout, clearTimeout, setInterval, clearInterval }
  const target: Timers = { ...original }
  const tracking = trackTimers(target as typeof globalThis)
  return { original, target, tracking }
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

describe('while a file runs', () => {
  it('behaves like Node\'s timer functions', async () => {
    const { target, tracking } = install()
    expect(await promisify(target.setTimeout)(1, 'value')).toBe('value')
    expect(() => target.setTimeout('not a function' as never)).toThrow(expect.objectContaining({ code: 'ERR_INVALID_ARG_TYPE' }))

    const receivers: unknown[] = []
    const handle = target.setTimeout(function (this: unknown) { receivers.push(this) }, 1)
    await wait(10)
    expect(receivers).toHaveLength(1)
    expect(receivers[0]).toBe(handle)

    let cleared = 0
    target.clearTimeout(target.setTimeout(() => { cleared++ }, 1))
    target.clearInterval(target.setInterval(() => { cleared++ }, 1))
    await wait(10)
    expect([cleared, tracking.pending()]).toEqual([0, 0])
    tracking.end()
  })

  it('tracks a timeout again when it is refreshed after it fired', async () => {
    const { target, tracking } = install()
    let runs = 0
    const handle = target.setTimeout(() => { runs++ }, 1)
    await wait(10)
    expect([runs, tracking.pending()]).toEqual([1, 0])

    handle.refresh()
    expect(tracking.pending()).toBe(1)
    tracking.end()
    await wait(10)
    expect(runs).toBe(1)
  })
})

describe('when the file ends', () => {
  it('clears the timeouts and intervals still pending and restores the originals', async () => {
    const { original, target, tracking } = install()
    let runs = 0
    target.setTimeout(() => { runs++ }, 5)
    target.setInterval(() => { runs++ }, 2)
    expect(tracking.pending()).toBe(2)

    tracking.end()
    await wait(20)
    expect([runs, tracking.pending()]).toEqual([0, 0])
    expect(target).toEqual(original)
  })

  it('runs nothing scheduled afterwards through a kept tracked function', async () => {
    const { target, tracking } = install()
    const { setTimeout: keptSetTimeout, setInterval: keptSetInterval } = target
    tracking.end()

    let runs = 0
    keptSetTimeout(() => { runs++ }, 1)
    keptSetInterval(() => { runs++ }, 1)
    await wait(10)
    expect([runs, tracking.pending()]).toEqual([0, 0])
  })

  it('does not stack when the next file installs it again', () => {
    const { original, target, tracking } = install()
    tracking.end()
    const next = trackTimers(target as typeof globalThis)
    next.end()
    expect(target).toEqual(original)
  })
})
