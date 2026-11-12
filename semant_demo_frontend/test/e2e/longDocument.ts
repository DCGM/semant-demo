import { expect, type Locator, type Page, type Route } from '@playwright/test'

/**
 * A test-only long document for the document context panel (#493): the passage reads of
 * one fixture document are answered as if it had `length` chunks. The fixture chunks in
 * `placed` keep their id and text (so their annotations stay marked) at the given order;
 * every other order is a long filler paragraph. The fixture corpus itself is unchanged, so
 * no other spec's counts move. Window reads of a placed chunk take the document metadata
 * from the real answer; `delay` (ms) holds every window answer back, to watch the panel
 * while a passage loads. `lead` (by chunk id) puts that many filler paragraphs before a
 * placed chunk's own text, making it tall with its annotations at its end; the workspace's
 * annotation rows are shifted to match.
 */
export async function longDocument (page: Page, options: { length: number, placed: Record<string, number>, delay?: number, lead?: Record<string, number> }) {
  const { length, placed, delay = 0, lead = {} } = options
  const padding = (id: string) => lead[id] ? Array.from({ length: lead[id] }, (_, i) => filler(i)).join('\n\n') + '\n\n' : ''
  const filler = (order: number) => `[Paragraph ${order}] ` +
    'Toho roku byla zima tuhá a sníh ležel až do dubna. Obecní rada se sešla v hostinci a jednala o opravě cesty k mlýnu. '.repeat(4)
  const real = new Map<string, Record<string, unknown>>()
  const orderOf = (id: string) => placed[id] ?? Number(/^filler-(\d+)$/.exec(id)?.[1] ?? Number.NaN)
  const idAt = (order: number) => Object.keys(placed).find(id => placed[id] === order) ?? `filler-${order}`
  const chunkAt = (order: number) => {
    const id = idAt(order)
    const template = real.get(id) ?? [...real.values()][0]
    return id.startsWith('filler-')
      ? { ...template, id, order, text: filler(order) }
      : { ...template, order, text: padding(id) + String(template.text) }
  }
  const range = (from: number, to: number) =>
    Array.from({ length: Math.max(0, Math.min(to, length - 1) - Math.max(from, 0) + 1) }, (_, i) => Math.max(from, 0) + i)
  const reads = { window: 0, adjacent: 0 }

  await page.route('**/api/documents/*/chunks/*/window*', async (route: Route) => {
    const url = new URL(route.request().url())
    const chunkId = decodeURIComponent(url.pathname.split('/')[5])
    if (!(chunkId in placed)) return route.continue()
    reads.window++
    const response = await route.fetch()
    const body = await response.json()
    for (const c of body.chunks as Record<string, unknown>[]) real.set(String(c.id), c)
    const at = placed[chunkId]
    const before = Number(url.searchParams.get('before') ?? 3)
    const after = Number(url.searchParams.get('after') ?? 3)
    const orders = range(at - before, at + after)
    body.chunks = orders.map(chunkAt)
    body.has_before = orders[0] > 0
    body.has_after = orders[orders.length - 1] < length - 1
    body.total_chunks = length
    if (delay) await new Promise(resolve => setTimeout(resolve, delay))
    await route.fulfill({ response, json: body })
  })

  await page.route('**/api/documents/*/chunks/*/adjacent*', async (route: Route) => {
    const url = new URL(route.request().url())
    const edge = orderOf(decodeURIComponent(url.pathname.split('/')[5]))
    if (Number.isNaN(edge)) return route.continue()
    reads.adjacent++
    const limit = Number(url.searchParams.get('limit') ?? 5)
    const orders = url.searchParams.get('direction') === 'before' ? range(edge - limit, edge - 1) : range(edge + 1, edge + limit)
    const more = url.searchParams.get('direction') === 'before' ? orders[0] > 0 : orders[orders.length - 1] < length - 1
    await route.fulfill({ json: { chunks: orders.map(chunkAt), has_more: orders.length > 0 && more } })
  })

  if (Object.keys(lead).length) {
    await page.route('**/api/user_collections/*/annotations?*', async (route: Route) => {
      const response = await route.fetch()
      const body = await response.json()
      for (const row of (body.rows ?? body.items ?? []) as Record<string, unknown>[]) {
        const shift = padding(String(row.chunk_id ?? row.chunkId)).length
        if (shift && typeof row.start === 'number' && typeof row.end === 'number') {
          row.start += shift
          row.end += shift
        }
      }
      await route.fulfill({ response, json: body })
    })
  }

  return reads
}

/** The element scrolling the sidebar panel's content. */
function scroller (panel: Locator) {
  return panel.evaluateHandle(el => {
    for (let node = el.parentElement; node; node = node.parentElement) {
      if (/(auto|scroll)/.test(getComputedStyle(node).overflowY)) return node
    }
    return document.scrollingElement as HTMLElement
  })
}

/**
 * The panel scroller's `scrollTop` in every frame from now until `stop()`. Starts once the
 * scroll has stood still for a moment, so an earlier scroll or layout shift (an extension
 * just shown) is not taken for the motion under test.
 */
export async function recordScroll (panel: Locator) {
  const handle = await scroller(panel)
  let previous = -1
  await expect.poll(async () => {
    const top = await handle.evaluate((el: Element) => Math.round(el.scrollTop))
    const still = top === previous
    previous = top
    return still
  }, { intervals: [250], timeout: 10_000 }).toBe(true)
  await handle.evaluate((el: Element) => {
    const w = window as unknown as { scrollTrace: number[], tracing: boolean }
    w.scrollTrace = [Math.round(el.scrollTop)]
    w.tracing = true
    const tick = () => {
      if (!w.tracing) return
      const top = Math.round(el.scrollTop)
      if (top !== w.scrollTrace[w.scrollTrace.length - 1]) w.scrollTrace.push(top)
      requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  })
  return {
    /** Waits until the scroll has settled; returns the distinct positions in order. */
    async stop (): Promise<number[]> {
      const page = panel.page()
      let last = -1
      await expect.poll(async () => {
        const now = await page.evaluate(() => (window as unknown as { scrollTrace: number[] }).scrollTrace.length)
        const settled = now === last
        last = now
        return settled
      }, { intervals: [300], timeout: 10_000 }).toBe(true)
      return page.evaluate(() => {
        const w = window as unknown as { scrollTrace: number[], tracing: boolean }
        w.tracing = false
        return w.scrollTrace
      })
    },
    /** The scroller's height (one screen of the panel). */
    height: () => handle.evaluate((el: Element) => el.clientHeight),
    /** Scrolls the panel to `top` at once. */
    scrollTo: (top: number) => handle.evaluate((el: Element, t: number) => { el.scrollTop = t }, top)
  }
}

/**
 * Splits a scroll trace into the instant jump (if any) and the animated rest: a step
 * larger than `jumpAbove` px between two frames is the jump. Returns where the animation
 * started and ended.
 */
export function animatedPart (trace: number[], jumpAbove: number): { jumped: boolean, from: number, to: number } {
  let start = 0
  for (let i = 1; i < trace.length; i++) if (Math.abs(trace[i] - trace[i - 1]) > jumpAbove) start = i
  return { jumped: start > 0, from: trace[start], to: trace[trace.length - 1] }
}
