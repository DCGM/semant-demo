<template>
  <div
    ref="viewer"
    class="scan-view"
    :class="{ 'scan-view--dragging': dragging, 'scan-view--over-line': hoverLineId !== null }"
    data-testid="scan-view"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerCancel"
    @pointerleave="hoverLineId = null"
    @wheel.prevent="onWheel"
    @dblclick="onDoubleClick"
  >
    <div
      v-if="src && stageSize"
      class="scan-view__stage"
      :class="{ 'scan-view__stage--animated': animated }"
      :style="stageStyle"
      data-testid="scan-stage"
    >
      <img
        :key="pageKey"
        class="scan-view__image"
        :src="src"
        :alt="imageAlt"
        draggable="false"
        @load="onImageLoad"
        @error="onImageError"
      />
      <svg
        v-if="layout && imageState === 'loaded'"
        class="scan-view__overlay"
        :viewBox="`0 0 ${overlaySize.width} ${overlaySize.height}`"
        preserveAspectRatio="none"
        aria-hidden="true"
        data-testid="scan-overlay"
        :data-layout-page-id="layout.pageId"
      >
        <polygon
          v-for="line in layout.lines"
          :key="line.id"
          class="scan-line"
          :class="{
            'scan-line--hover': line.id === hoverLineId,
            'scan-line--active': line.id === activeLineId
          }"
          :points="svgPoints(line.polygon)"
          :data-line-id="line.id"
        />
        <polygon
          v-for="h in highlightBands"
          :key="h.key"
          class="scan-highlight"
          :points="h.points"
          :data-highlight-line-id="h.lineId"
        />
      </svg>
    </div>
    <!-- Hidden until the size is known (no manifest size): only loads the image. -->
    <img
      v-else-if="src"
      :key="`probe-${pageKey}`"
      class="scan-view__probe"
      :src="src"
      alt=""
      @load="onImageLoad"
      @error="onImageError"
    />
    <div v-if="src && imageState === 'loading'" class="scan-view__state">
      <q-spinner size="32px" color="primary" />
      <span class="q-ml-sm">Loading the scan…</span>
    </div>
    <div v-else-if="src && imageState === 'error'" class="scan-view__state text-negative" role="alert">
      <q-icon name="broken_image" size="24px" class="q-mr-sm" />
      The scan of this page could not be loaded.
      <q-btn flat dense no-caps color="primary" label="Retry" class="q-ml-sm" @click.stop="retry" @pointerdown.stop />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  distanceAlong, lineAt, lineBand, offsetAtDistance, polygonBounds, rangeDistances, svgPoints,
  type PageLayout, type Point, type Rect, type ScanLine
} from './pageLayout'
import {
  clampTransform, fitTransform, keepCenter, scaleLimits, smartFocus, toScan, zoomAt, ZOOM_STEP,
  type Size, type Transform
} from './viewport'

// One whole page scan with its OCR line overlay. The image and the overlay are drawn in
// scan pixels inside one element moved by a single transform (viewport.ts), so they stay
// aligned under zoom, pan, fit, resize and page changes. Lines are hit-tested from the
// layout geometry, not from the DOM. The owner (DocumentImagePane) decides which page,
// layout and highlights are shown; this view owns only the transform.

export interface LineHighlight {
  lineId: string
  /** UTF-16 offsets in the line's text; widened to whole (approximate) words. */
  start?: number
  end?: number
}

const props = withDefaults(defineProps<{
  /** Identity of the shown page; a new key resets the view. */
  pageKey: string
  src: string | null
  /** The scan size when known in advance (manifest); else read from the image. */
  size?: Size | null
  layout?: PageLayout | null
  activeLineId?: string | null
  highlights?: LineHighlight[]
  imageAlt?: string
}>(), { size: null, layout: null, activeLineId: null, highlights: () => [], imageAlt: 'Page scan' })

const emit = defineEmits<{
  /** A click on an OCR line; `offset` is the approximate start of the word clicked, if known. */
  lineClick: [target: { lineId: string, offset?: number }]
  /** Zoom as a percentage of the scan's own pixels. */
  zoom: [percent: number]
  imageState: [state: 'loading' | 'loaded' | 'error']
}>()

const viewer = ref<HTMLElement | null>(null)
const viewerSize = ref<Size>({ width: 0, height: 0 })
const naturalSize = ref<Size | null>(null)
const imageState = ref<'loading' | 'loaded' | 'error'>('loading')
const transform = ref<Transform>({ scale: 1, x: 0, y: 0 })
/** The page is fitted: a resize fits it again instead of keeping the center. */
const fitted = ref(true)
const animated = ref(false)
const dragging = ref(false)
const hoverLineId = ref<string | null>(null)
let pendingFocus: { lineIds: string[], start?: number, end?: number } | null = null

const stageSize = computed<Size | null>(() => naturalSize.value ?? (props.size && props.size.width > 0 && props.size.height > 0 ? props.size : null))
/** The coordinates of the layout file (its scan size), mapped onto the stage. */
const overlaySize = computed<Size>(() => props.layout?.image ?? stageSize.value ?? { width: 1, height: 1 })
const overlayScale = computed(() => stageSize.value ? stageSize.value.width / overlaySize.value.width : 1)

const stageStyle = computed(() => {
  const s = stageSize.value!
  const t = transform.value
  return {
    width: `${s.width}px`,
    height: `${s.height}px`,
    transform: `translate(${t.x}px, ${t.y}px) scale(${t.scale})`
  }
})

const linesById = computed(() => new Map((props.layout?.lines ?? []).map(l => [l.id, l])))

const highlightBands = computed(() => props.highlights.flatMap((h, i) => {
  const line = linesById.value.get(h.lineId)
  if (!line) return []
  const [from, to] = rangeDistances(line, h.start, h.end)
  return [{ key: `${i}-${h.lineId}`, lineId: h.lineId, points: svgPoints(lineBand(line, from, to)) }]
}))

const limits = () => stageSize.value ? scaleLimits(stageSize.value, viewerSize.value) : { min: 0.01, max: 4 }

function setTransform (t: Transform, options: { animate?: boolean, fitted?: boolean } = {}) {
  const s = stageSize.value
  transform.value = s ? clampTransform(t, s, viewerSize.value) : t
  fitted.value = options.fitted ?? false
  animated.value = options.animate ?? false
  emit('zoom', Math.round(transform.value.scale * 100))
}

function fit (animate = false) {
  if (!stageSize.value) return
  setTransform(fitTransform(stageSize.value, viewerSize.value), { animate, fitted: true })
}

function zoomBy (factor: number, anchor?: Point) {
  if (!stageSize.value) return
  const a = anchor ?? [viewerSize.value.width / 2, viewerSize.value.height / 2] as Point
  setTransform(zoomAt(transform.value, factor, a, limits()), { animate: !anchor })
}

const zoomIn = () => zoomBy(ZOOM_STEP)
const zoomOut = () => zoomBy(1 / ZOOM_STEP)

/** A rectangle of the layout's coordinates in stage pixels. */
function toStage (r: Rect): Rect {
  const k = overlayScale.value
  return { x: r.x * k, y: r.y * k, width: r.width * k, height: r.height * k }
}

function applyFocus (lineIds: string[], start?: number, end?: number): boolean {
  const lines = lineIds.map(id => linesById.value.get(id)).filter((l): l is ScanLine => !!l)
  if (!lines.length || !stageSize.value || imageState.value !== 'loaded' || viewerSize.value.width === 0) return false
  // The beginning of the target: its first line (part of it with word offsets).
  const first = lines[0]
  const [from, to] = rangeDistances(first, start, lines.length === 1 ? end : undefined)
  const rect = toStage(polygonBounds(lineBand(first, from, to)))
  const next = smartFocus(transform.value, rect, viewerSize.value, {
    limits: limits(),
    minReadableHeight: 10,
    readableHeight: 22
  })
  if (next) setTransform(next, { animate: true })
  return true
}

/**
 * Bring the lines into view when they are not visible enough (smart focus): the first of
 * them, or its part `[start, end)`. Waits for the image when it is still loading.
 */
function focusLines (lineIds: string[], range: { start?: number, end?: number } = {}) {
  pendingFocus = null
  if (!applyFocus(lineIds, range.start, range.end)) pendingFocus = { lineIds, ...range }
}

function onImageLoad (e: Event) {
  const img = e.target as HTMLImageElement
  if (img.naturalWidth > 0 && img.naturalHeight > 0 &&
      (stageSize.value?.width !== img.naturalWidth || stageSize.value?.height !== img.naturalHeight)) {
    naturalSize.value = { width: img.naturalWidth, height: img.naturalHeight }
  }
  imageState.value = 'loaded'
  emit('imageState', 'loaded')
  if (fitted.value) fit()
  if (pendingFocus) {
    const p = pendingFocus
    pendingFocus = null
    focusLines(p.lineIds, p)
  }
}

function onImageError () {
  imageState.value = 'error'
  emit('imageState', 'error')
}

function retry () {
  imageState.value = 'loading'
  emit('imageState', 'loading')
  // Re-requesting the same URL: reset the source on the image element.
  const img = viewer.value?.querySelector<HTMLImageElement>('img')
  if (img && props.src) {
    img.src = ''
    img.src = props.src
  }
}

watch(() => [props.pageKey, props.src], () => {
  naturalSize.value = null
  imageState.value = props.src ? 'loading' : 'error'
  hoverLineId.value = null
  pendingFocus = null
  emit('imageState', imageState.value)
  fit()
  fitted.value = true
}, { immediate: false })

watch(() => props.size, () => { if (fitted.value) fit() })

// --- pointer: drag to pan, two fingers to zoom, click a line --------------------------

const pointers = new Map<number, Point>()
let pressStart: Point | null = null
let moved = false
let pinch: { distance: number, transform: Transform } | null = null
const CLICK_SLOP = 5

function local (e: { clientX: number, clientY: number }): Point {
  const box = viewer.value!.getBoundingClientRect()
  return [e.clientX - box.left, e.clientY - box.top]
}

function lineUnder (p: Point): ScanLine | null {
  if (!props.layout || imageState.value !== 'loaded') return null
  const [sx, sy] = toScan(transform.value, p)
  const k = overlayScale.value
  // A few screen pixels of tolerance, in layout pixels.
  return lineAt(props.layout.lines, [sx / k, sy / k], 4 / (transform.value.scale * k))
}

function onPointerDown (e: PointerEvent) {
  if (e.button !== 0 || !stageSize.value) return
  if ((e.target as Element | null)?.closest?.('button')) return
  viewer.value?.setPointerCapture?.(e.pointerId)
  pointers.set(e.pointerId, local(e))
  if (pointers.size === 1) {
    pressStart = local(e)
    moved = false
  } else if (pointers.size === 2) {
    const [a, b] = [...pointers.values()]
    pinch = { distance: Math.hypot(a[0] - b[0], a[1] - b[1]), transform: transform.value }
    moved = true
  }
}

function onPointerMove (e: PointerEvent) {
  const p = local(e)
  if (!pointers.has(e.pointerId)) {
    if (e.pointerType === 'mouse') hoverLineId.value = lineUnder(p)?.id ?? null
    return
  }
  const previous = pointers.get(e.pointerId)!
  pointers.set(e.pointerId, p)
  if (pinch && pointers.size >= 2) {
    const [a, b] = [...pointers.values()]
    const distance = Math.hypot(a[0] - b[0], a[1] - b[1])
    const mid: Point = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
    if (pinch.distance > 0) setTransform(zoomAt(pinch.transform, distance / pinch.distance, mid, limits()))
    return
  }
  if (!moved && pressStart && Math.hypot(p[0] - pressStart[0], p[1] - pressStart[1]) > CLICK_SLOP) {
    moved = true
    dragging.value = true
  }
  if (moved) {
    const t = transform.value
    setTransform({ scale: t.scale, x: t.x + p[0] - previous[0], y: t.y + p[1] - previous[1] })
  }
}

function endPointer (e: PointerEvent) {
  pointers.delete(e.pointerId)
  if (pointers.size < 2) pinch = null
  if (pointers.size === 0) {
    dragging.value = false
    pressStart = null
  }
}

function onPointerUp (e: PointerEvent) {
  const wasClick = pointers.has(e.pointerId) && pointers.size === 1 && !moved
  endPointer(e)
  if (!wasClick) return
  const p = local(e)
  const line = lineUnder(p)
  if (!line) return
  const [sx, sy] = toScan(transform.value, p)
  const k = overlayScale.value
  const offset = offsetAtDistance(line, distanceAlong(line, [sx / k, sy / k]))
  emit('lineClick', offset === undefined ? { lineId: line.id } : { lineId: line.id, offset })
}

function onPointerCancel (e: PointerEvent) {
  endPointer(e)
}

function onWheel (e: WheelEvent) {
  if (!stageSize.value) return
  // Pixel, line and page delta modes; one notch of a mouse wheel is about one zoom step.
  const delta = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1)
  zoomBy(Math.pow(ZOOM_STEP, -delta / 100), local(e))
}

function onDoubleClick (e: MouseEvent) {
  if ((e.target as Element | null)?.closest?.('button')) return
  zoomBy(ZOOM_STEP * ZOOM_STEP, local(e))
}

// --- resize: refit a fitted page, else keep the center ---------------------------------

let observer: ResizeObserver | null = null

function measure () {
  const el = viewer.value
  if (!el) return
  const next = { width: el.clientWidth, height: el.clientHeight }
  const before = viewerSize.value
  if (next.width === before.width && next.height === before.height) return
  viewerSize.value = next
  if (fitted.value || before.width === 0 || before.height === 0) fit()
  else setTransform(keepCenter(transform.value, before, next))
  if (pendingFocus) {
    const p = pendingFocus
    focusLines(p.lineIds, p)
  }
}

onMounted(() => {
  measure()
  emit('imageState', imageState.value)
  if (typeof ResizeObserver !== 'undefined' && viewer.value) {
    observer = new ResizeObserver(measure)
    observer.observe(viewer.value)
  }
})

onBeforeUnmount(() => observer?.disconnect())

defineExpose({
  zoomIn,
  zoomOut,
  fit: () => fit(true),
  focusLines,
  /** Current transform and viewer size, for tests and owners. */
  view: () => ({ transform: transform.value, viewer: viewerSize.value, fitted: fitted.value })
})
</script>

<style scoped>
.scan-view {
  position: relative;
  overflow: hidden;
  width: 100%;
  height: 100%;
  background: #e9e6df;
  touch-action: none;
  user-select: none;
  cursor: grab;
}

.scan-view--dragging {
  cursor: grabbing;
}

.scan-view--over-line:not(.scan-view--dragging) {
  cursor: pointer;
}

.scan-view__stage {
  position: absolute;
  top: 0;
  left: 0;
  transform-origin: 0 0;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.25);
  background: #fff;
}

.scan-view__stage--animated {
  transition: transform 0.18s ease-out;
}

@media (prefers-reduced-motion: reduce) {
  .scan-view__stage--animated {
    transition: none;
  }
}

.scan-view__image,
.scan-view__overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.scan-view__image {
  display: block;
  pointer-events: none;
}

.scan-view__probe {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.scan-view__overlay {
  pointer-events: none;
  overflow: visible;
}

.scan-line {
  fill: transparent;
  stroke: transparent;
  vector-effect: non-scaling-stroke;
}

.scan-line--hover {
  fill: rgba(25, 118, 210, 0.08);
  stroke: rgba(25, 118, 210, 0.55);
  stroke-width: 1px;
}

.scan-line--active {
  fill: rgba(25, 118, 210, 0.14);
  stroke: rgb(25, 118, 210);
  stroke-width: 2px;
}

.scan-highlight {
  fill: rgba(255, 193, 7, 0.35);
  stroke: rgba(230, 160, 0, 0.9);
  stroke-width: 1px;
  vector-effect: non-scaling-stroke;
}

.scan-view__state {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  text-align: center;
  pointer-events: none;
}

.scan-view__state .q-btn {
  pointer-events: auto;
}
</style>
