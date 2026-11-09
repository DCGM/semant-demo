import { readFileSync } from 'fs'
import { join } from 'path'
import { expect, test, type Page } from '@playwright/test'

import { closePhoneNavigation, useViewport } from './support'

// The scan viewer (#543) on real scans (#546): two downscaled pages of the real-page
// fixtures (semant_demo_backend/tests/real_pages.py) and the page files the converter made
// of their PERO OCR: a 1913 newspaper page in columns with curved and skewed lines and a
// text page of a 1906 volume. The documents are not in the test store; their page manifest and assets are served
// by request routing, as the backend would serve them. The scans are smaller than the scan
// the geometry refers to, so the viewer scales the overlay.
//
// On the book page what is checked is the scan's ink, not the layout file: every line's
// band, as it is on screen after zoom, pan and resize, lies on the darkest part of the scan
// around it. The newspaper's small print and ruled boxes make such a profile ambiguous, so
// there its most curved and most skewed bands are compared with their baselines instead.

const FIXTURE = join(__dirname, '../../../semant_demo_backend/tests/fixtures/real_pages')
const NEWSPAPER = '0002097a-2223-46b0-8507-bde4b059daaa'
const BOOK = '00094a56-54af-4bd4-9559-c5601d81b15d'

interface FixturePage { pageId: string, label: string | null, pageType: string }
const documents = (JSON.parse(readFileSync(join(FIXTURE, 'documents.json'), 'utf8')) as {
  documents: { documentId: string, pages: FixturePage[] }[]
}).documents

const scanPath = (documentId: string, pageId: string) => join(FIXTURE, 'scans', documentId, `${pageId}.jpg`)
const layoutPath = (documentId: string, pageId: string) => join(FIXTURE, 'generated/pages', documentId, `${pageId}.json`)
const hasScan = (documentId: string, pageId: string) => {
  try { readFileSync(scanPath(documentId, pageId)); return true } catch { return false }
}

/** Serve one fixture document's page manifest, layouts and scans the way the backend does. */
async function serveDocument (page: Page, documentId: string): Promise<string> {
  const pages = documents.find(d => d.documentId === documentId)!.pages
  const base = `/api/documents/${documentId}/pages`
  const manifest = {
    document_id: documentId,
    available: true,
    pages: pages.map((p, order) => {
      const layout = JSON.parse(readFileSync(layoutPath(documentId, p.pageId), 'utf8')) as { image: { width: number, height: number } | null }
      const scan = hasScan(documentId, p.pageId)
      return {
        page_id: p.pageId,
        order,
        label: p.label,
        page_type: p.pageType,
        // The size of the original scan, which the geometry refers to (as the import records it).
        width: layout.image?.width ?? null,
        height: layout.image?.height ?? null,
        image_url: scan ? `${base}/${p.pageId}/image` : null,
        layout_url: `${base}/${p.pageId}/layout`,
        thumbnail_url: scan ? `${base}/${p.pageId}/thumbnail` : null
      }
    })
  }
  await page.route(`**/api/documents/${documentId}`, route => route.fulfill({ status: 404, json: { detail: 'Document not found' } }))
  await page.route(`**${base}`, route => route.fulfill({ json: manifest }))
  await page.route(`**${base}/*/*`, route => {
    const [pageId, kind] = new URL(route.request().url()).pathname.split('/').slice(-2)
    if (kind === 'layout') return route.fulfill({ contentType: 'application/json', body: readFileSync(layoutPath(documentId, pageId)) })
    return route.fulfill({ contentType: 'image/jpeg', body: readFileSync(scanPath(documentId, pageId)) })
  })
  return manifest.pages.find(p => p.image_url)!.page_id
}

const viewport = (page: Page) => page.getByTestId('scan-viewport')
const stage = (page: Page) => page.getByTestId('scan-stage')
const image = (page: Page) => page.locator('img.scan-view__image')

async function openScan (page: Page, documentId: string) {
  const pageId = await serveDocument(page, documentId)
  await page.goto(`/#/preview/scan/${documentId}?page=${pageId}`)
  await closePhoneNavigation(page)
  await expect(page.getByTestId('document-image-pane')).toBeVisible()
  return pageId
}

async function settled (page: Page) {
  await expect.poll(() => image(page).evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true)
  await expect(page.locator('polygon.scan-line').first()).toBeAttached()
  let last = ''
  await expect.poll(async () => {
    const now = await stage(page).evaluate(el => getComputedStyle(el).transform)
    const same = now === last
    last = now
    return same
  }).toBe(true)
}

interface Ink {
  /** Bands measured: on screen vertically, with at least 40 px of their width in the viewer,
   * and at least 8 px high in the scan's own pixels (smaller print, e.g. a newspaper's body
   * text in the downscaled scan, is too coarse to locate within a fraction of a band). */
  lines: number
  /** Bands whose darkest position is within 0.2 band heights of where they are drawn. */
  onInk: number
}

const SHIFTS = Array.from({ length: 13 }, (_, i) => (i - 6) / 10) // -0.6 .. +0.6 band heights

/**
 * For each line band of the overlay: its polygon mapped to the screen by the browser (the
 * stage transform and the overlay's scale), then into the scan's pixels through the image's
 * on-screen box. The scan's mean darkness under the band is measured with the band moved up
 * and down by up to 0.6 of its height; a band on its printed line is darkest where it is.
 * `misalign` (in band heights) measures as if every band were drawn that much lower.
 */
async function ink (page: Page, misalign = 0): Promise<Ink> {
  return page.evaluate(({ shifts, misalign }) => {
    const img = document.querySelector<HTMLImageElement>('img.scan-view__image')!
    const box = img.getBoundingClientRect()
    const view = document.querySelector('[data-testid="scan-viewport"]')!.getBoundingClientRect()
    const canvas = document.createElement('canvas')
    canvas.width = img.naturalWidth
    canvas.height = img.naturalHeight
    const ctx = canvas.getContext('2d', { willReadFrequently: true })!
    ctx.drawImage(img, 0, 0)
    const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data
    const darkness = (sx: number, sy: number) => {
      const x = Math.floor((sx - box.left) * img.naturalWidth / box.width)
      const y = Math.floor((sy - box.top) * img.naturalHeight / box.height)
      if (x < 0 || y < 0 || x >= canvas.width || y >= canvas.height) return null
      return 255 - pixels[(y * canvas.width + x) * 4]
    }
    const inside = (pts: DOMPoint[], x: number, y: number) => {
      let hit = false
      for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
        if ((pts[i].y > y) !== (pts[j].y > y) && x < (pts[j].x - pts[i].x) * (y - pts[i].y) / (pts[j].y - pts[i].y) + pts[i].x) hit = !hit
      }
      return hit
    }
    let lines = 0
    let onInk = 0
    for (const polygon of Array.from(document.querySelectorAll<SVGPolygonElement>('polygon.scan-line'))) {
      const m = polygon.getScreenCTM()!
      const pts = Array.from({ length: polygon.points.numberOfItems }, (_, i) => {
        const p = polygon.points.getItem(i)
        return new DOMPoint(p.x, p.y).matrixTransform(m)
      })
      const ys = pts.map(p => p.y)
      const top = Math.min(...ys)
      const bottom = Math.max(...ys)
      const height = bottom - top
      const left = Math.max(view.left, Math.min(...pts.map(p => p.x)))
      const right = Math.min(view.right, Math.max(...pts.map(p => p.x)))
      if (top < view.top || bottom > view.bottom || right - left < 40) continue
      if (height * img.naturalHeight / box.height < 8) continue
      // The points inside the band, about 4,000 at most.
      const step = Math.max(1, Math.sqrt((right - left) * height / 4000))
      const points: [number, number][] = []
      for (let y = top; y <= bottom; y += step) {
        for (let x = left; x <= right; x += step) if (inside(pts, x, y)) points.push([x, y])
      }
      const profile = shifts.map((k) => {
        let sum = 0
        let n = 0
        for (const [x, y] of points) {
          const d = darkness(x, y + (k + misalign) * height)
          if (d !== null) { sum += d; n++ }
        }
        return n ? sum / n : 0
      })
      const best = shifts[profile.indexOf(Math.max(...profile))]
      lines++
      if (Math.abs(best) <= 0.2) onInk++
    }
    return { lines, onInk }
  }, { shifts: SHIFTS, misalign })
}

async function expectOnTheInk (page: Page, minimumLines: number) {
  const r = await ink(page)
  expect(r.lines).toBeGreaterThanOrEqual(minimumLines)
  // Most bands are darkest where they are drawn (measured on this page: 75-100 % per step;
  // bands drawn 0.4 of a band off: 0-17 %, see the next test).
  expect(r.onInk / r.lines).toBeGreaterThan(0.7)
}

interface LayoutLine { id: string, baseline: [number, number][], heights: [number, number] | null }

/** The newspaper page's lines with the most curved and the most skewed baselines. */
function irregularLines (documentId: string, pageId: string) {
  const layout = JSON.parse(readFileSync(layoutPath(documentId, pageId), 'utf8')) as {
    image: { width: number }, regions: { lines: LayoutLine[] }[]
  }
  const lines = layout.regions.flatMap(r => r.lines).filter(l => l.heights && l.baseline.length > 2)
  const length = (l: LayoutLine) => Math.hypot(l.baseline.at(-1)![0] - l.baseline[0][0], l.baseline.at(-1)![1] - l.baseline[0][1])
  const skew = (l: LayoutLine) => Math.abs(l.baseline.at(-1)![1] - l.baseline[0][1]) / length(l)
  const sag = (l: LayoutLine) => {
    const [[x0, y0], [x1, y1]] = [l.baseline[0], l.baseline.at(-1)!]
    return Math.max(...l.baseline.map(([x, y]) => Math.abs((x1 - x0) * (y0 - y) - (x0 - x) * (y1 - y0)) / length(l)))
  }
  const long = lines.filter(l => length(l) > 300)
  const curved = [...long].sort((a, b) => sag(b) - sag(a))[0]
  const skewed = [...long].sort((a, b) => skew(b) - skew(a))[0]
  return { width: layout.image.width, lines: [curved, skewed], sag: sag(curved), skew: skew(skewed) }
}

/**
 * The band of each line covers its baseline (± its heights) from the layout file, mapped
 * through the image's on-screen box: the downscaled scan and the overlay drawn in the
 * original scan's pixels agree on screen.
 */
async function expectBandsOnBaselines (page: Page, lines: LayoutLine[], layoutWidth: number) {
  const box = (await image(page).boundingBox())!
  const k = box.width / layoutWidth
  for (const l of lines) {
    const band = (await page.locator(`polygon.scan-line[data-line-id="${l.id}"]`).boundingBox())!
    const xs = l.baseline.map(p => p[0])
    const ys = l.baseline.map(p => p[1])
    const slack = 2 + 0.05 * (Math.max(...ys) - Math.min(...ys) + l.heights![0] + l.heights![1]) * k
    expect(Math.abs(band.x - (box.x + Math.min(...xs) * k))).toBeLessThan(slack + l.heights![0] * k)
    expect(Math.abs(band.x + band.width - (box.x + Math.max(...xs) * k))).toBeLessThan(slack + l.heights![0] * k)
    expect(Math.abs(band.y - (box.y + (Math.min(...ys) - l.heights![0]) * k))).toBeLessThan(slack)
    expect(Math.abs(band.y + band.height - (box.y + (Math.max(...ys) + l.heights![1]) * k))).toBeLessThan(slack)
  }
}

/** Zoom, pan, wheel zoom, resize, fit and phone width, checking `check` after each. */
async function throughViewChanges (page: Page, check: (step: string) => Promise<void>) {
  await check('fitted')
  await viewport(page).focus()
  for (let i = 0; i < 3; i++) await page.keyboard.press('+')
  await settled(page)
  await check('zoomed')
  const v = (await viewport(page).boundingBox())!
  await page.mouse.move(v.x + v.width / 2, v.y + v.height / 2)
  await page.mouse.down()
  await page.mouse.move(v.x + v.width / 2 - 170, v.y + v.height / 2 - 230, { steps: 6 })
  await page.mouse.up()
  await settled(page)
  await check('panned')
  await page.mouse.wheel(0, -300)
  await settled(page)
  await check('wheel-zoomed')
  await page.setViewportSize({ width: 1000, height: 760 })
  await settled(page)
  await check('resized')
  await page.keyboard.press('0')
  await settled(page)
  await check('fitted again')
  await useViewport(page, 'phone')
  await settled(page)
  await check('phone')
}

test('real book scan: every line band lies on its printed line through zoom, pan and resize', async ({ page }) => {
  await useViewport(page, 'wide')
  await openScan(page, BOOK)
  await settled(page)
  const minimum: Record<string, number> = { fitted: 35, zoomed: 10, panned: 10, 'wheel-zoomed': 3, resized: 3, 'fitted again': 35, phone: 20 }
  await throughViewChanges(page, step => test.step(step, () => expectOnTheInk(page, minimum[step])))
})

test('real book scan: the ink check fails for bands drawn 0.4 of a band off their lines', async ({ page }) => {
  await useViewport(page, 'wide')
  await openScan(page, BOOK)
  await settled(page)
  for (const misalign of [0.4, -0.4]) {
    const off = await ink(page, misalign)
    expect(off.lines).toBeGreaterThanOrEqual(35)
    expect(off.onInk / off.lines).toBeLessThan(0.3)
  }
  // The excerpt's other pages have no scan: the viewer says so, and has no lines to show.
  await page.getByRole('button', { name: 'Previous page' }).click()
  await expect(page.getByText('No scan of this page is available.')).toBeVisible()
  await expect(image(page)).toHaveCount(0)
})

test('real newspaper scan: curved and skewed bands follow their baselines on the downscaled scan', async ({ page }) => {
  await useViewport(page, 'wide')
  const pageId = await openScan(page, NEWSPAPER)
  await settled(page)
  const { width, lines, sag, skew } = irregularLines(NEWSPAPER, pageId)
  // Real irregular lines: a baseline sagging by tens of pixels, one rising by over 10 %.
  expect(sag).toBeGreaterThan(30)
  expect(skew).toBeGreaterThan(0.1)
  // The scan served is smaller than the scan the geometry refers to.
  expect(await image(page).evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeLessThan(width / 2)
  await throughViewChanges(page, async (step) => {
    await test.step(step, async () => {
      for (const l of lines) await page.locator(`polygon.scan-line[data-line-id="${l.id}"]`).scrollIntoViewIfNeeded().catch(() => undefined)
      const visible = []
      const view = (await viewport(page).boundingBox())!
      for (const l of lines) {
        const b = await page.locator(`polygon.scan-line[data-line-id="${l.id}"]`).boundingBox()
        if (b && b.x >= view.x && b.y >= view.y && b.x + b.width <= view.x + view.width && b.y + b.height <= view.y + view.height) visible.push(l)
      }
      await expectBandsOnBaselines(page, step.startsWith('fitted') ? lines : visible, width)
      if (step.startsWith('fitted')) expect(visible).toHaveLength(2)
    })
  })
})
