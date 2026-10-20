<template>
  <div ref="column" class="span-gutter-column" :style="{ width: width + 'px' }">
    <!-- The gutter is as tall as the document, so a native scrollbar would usually be off
         screen (and hidden until used with overlay scrollbars). This one sits at the top
         and sticks below the reader toolbar while the document scrolls. -->
    <div v-if="overflowing" class="span-gutter-scrollbar" @pointerdown="onTrackPointerDown">
      <div
        class="span-gutter-thumb"
        :style="{ width: thumbWidth + 'px', right: thumbRight + 'px' }"
        @pointerdown.stop="onThumbPointerDown"
        @pointermove="onThumbPointerMove"
        @pointerup="onThumbPointerUp"
        @pointercancel="onThumbPointerUp"
      ></div>
    </div>
    <div ref="viewport" class="span-gutter-wrapper" @scroll="onViewportScroll">
      <div class="span-gutter" :style="{ width: labelsWidth + 'px', height: gutterHeight + 'px' }">
        <div
          v-for="item in markers"
          :key="item.spanId"
          class="gutter-item"
          :class="markerClasses(item)"
          :style="{
            top: item.top + 'px',
            height: item.height + 'px',
            right: item.column * COLUMN_WIDTH + GUTTER_PADDING + 'px',
            '--tag-color': tagInfo(item.tagId).color
          }"
          :title="markerTitle(item)"
          @mouseenter="emit('hover', item.spanId)"
          @mouseleave="emit('hover', null)"
          @click.stop="emit('select', item, $event)"
        >
          <q-icon v-if="item.isAuto" name="auto_awesome" size="10px" class="gutter-icon" />
          <span class="gutter-shorthand">{{ tagInfo(item.tagId).shorthand }}</span>
        </div>
      </div>
    </div>
    <!-- Dragging the right border changes the split between the gutter and the text. -->
    <div
      class="span-gutter-resizer"
      :class="{ 'is-dragging': resizeStart }"
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the span gutter"
      tabindex="0"
      @pointerdown.prevent="onResizePointerDown"
      @pointermove="onResizePointerMove"
      @pointerup="onResizePointerUp"
      @pointercancel="onResizePointerUp"
      @keydown.left.prevent="resizeBy(-RESIZE_KEY_STEP)"
      @keydown.right.prevent="resizeBy(RESIZE_KEY_STEP)"
    ></div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { Tag } from 'src/generated/api'
import type { SpanMarker } from './AnnotationGutterTypes'

// Span markers left of the document text, one column per span sharing lines with another,
// column 0 next to the text. Each marker is a fixed-width block from the span's first line
// to its last with the shorthand centred; AI suggestions are dashed. More columns than
// fit are scrolled to with a scrollbar kept in view, starting at the text side; the wheel
// over the gutter scrolls the document, never the gutter sideways. Its right border can
// be dragged to make it wider or narrower; the width is remembered in this browser.
const props = defineProps<{
  markers: SpanMarker[]
  tags: Tag[]
  hoveredSpanId: string | null
  highlightedSpanId: string | null
}>()

const emit = defineEmits<{
  hover: [spanId: string | null]
  select: [marker: SpanMarker, event: MouseEvent]
}>()

const COLUMN_WIDTH = 50
const GUTTER_PADDING = 4
const UNKNOWN_TAG = { name: 'Unknown tag', color: '#3b82f6', shorthand: '?' }

const tagInfoMap = computed(() => {
  const map: Record<string, { name: string; color: string; shorthand: string }> = {}
  for (const tag of props.tags) {
    map[tag.id] = { name: tag.name, color: tag.color, shorthand: tag.shorthand || tag.name.slice(0, 3) }
  }
  return map
})

const tagInfo = (tagId: string) => tagInfoMap.value[tagId] ?? UNKNOWN_TAG

const columnCount = computed(() => props.markers.length ? Math.max(...props.markers.map(i => i.column)) + 1 : 0)
const labelsWidth = computed(() => columnCount.value * COLUMN_WIDTH + GUTTER_PADDING)

const markerClasses = (item: SpanMarker) => ({
  'is-active': props.hoveredSpanId === item.spanId,
  'is-auto': item.isAuto,
  'is-highlighted': props.highlightedSpanId === item.spanId
})

const markerTitle = (item: SpanMarker) => tagInfo(item.tagId).name + (item.isAuto ? ' (AI suggestion)' : '')

const gutterHeight = computed(() => {
  if (!props.markers.length) return 0
  return Math.max(...props.markers.map(i => i.top + i.height))
})

const viewport = ref<HTMLElement | null>(null)
const viewportWidth = ref(0)
// `direction: rtl`: 0 with column 0 in view, negative further out.
const scrollLeft = ref(0)
const maxScroll = computed(() => Math.max(0, labelsWidth.value - viewportWidth.value))
const overflowing = computed(() => maxScroll.value > 1)

const MIN_THUMB_WIDTH = 24
const thumbWidth = computed(() =>
  Math.max(MIN_THUMB_WIDTH, viewportWidth.value * viewportWidth.value / Math.max(labelsWidth.value, 1)))
const thumbTravel = computed(() => Math.max(0, viewportWidth.value - thumbWidth.value))
const thumbRight = computed(() => maxScroll.value ? -scrollLeft.value / maxScroll.value * thumbTravel.value : 0)

function onViewportScroll () {
  scrollLeft.value = viewport.value?.scrollLeft ?? 0
}

function scrollGutterTo (left: number) {
  if (viewport.value) viewport.value.scrollLeft = Math.min(0, Math.max(-maxScroll.value, left))
}

let dragStart: { x: number; scrollLeft: number } | null = null
function onThumbPointerDown (event: PointerEvent) {
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  dragStart = { x: event.clientX, scrollLeft: scrollLeft.value }
}

function onThumbPointerMove (event: PointerEvent) {
  if (!dragStart || !thumbTravel.value) return
  scrollGutterTo(dragStart.scrollLeft + (event.clientX - dragStart.x) * maxScroll.value / thumbTravel.value)
}

function onThumbPointerUp () {
  dragStart = null
}

// A click beside the thumb pages one gutter width that way.
function onTrackPointerDown (event: PointerEvent) {
  const thumb = (event.currentTarget as HTMLElement).firstElementChild?.getBoundingClientRect()
  if (!thumb) return
  scrollGutterTo(scrollLeft.value + (event.clientX < thumb.left ? -1 : 1) * viewportWidth.value)
}

const column = ref<HTMLElement | null>(null)
const WIDTH_STORAGE_KEY = 'semant.spanGutterWidth'
const DEFAULT_WIDTH = 232 // four columns
const PHONE_WIDTH = 120 // two columns
const MAX_WIDTH_SHARE = 0.6 // of the gutter and the text together
const RESIZE_KEY_STEP = COLUMN_WIDTH / 2
const minWidth = COLUMN_WIDTH + 2 * GUTTER_PADDING

function storedWidth (): number | null {
  try {
    const value = Number(localStorage.getItem(WIDTH_STORAGE_KEY))
    return value > 0 ? value : null
  } catch {
    return null
  }
}

function storeWidth (value: number) {
  try {
    localStorage.setItem(WIDTH_STORAGE_KEY, String(Math.round(value)))
  } catch {
    // Storage unavailable (private mode, quota): the width just won't persist.
  }
}

const isPhone = () => window.matchMedia('(max-width: 599px)').matches
const width = ref(isPhone() ? PHONE_WIDTH : storedWidth() ?? DEFAULT_WIDTH)

function clampWidth (value: number): number {
  const available = column.value?.parentElement?.clientWidth ?? Infinity
  return Math.round(Math.max(minWidth, Math.min(available * MAX_WIDTH_SHARE, value)))
}

function resizeBy (delta: number) {
  width.value = clampWidth(width.value + delta)
  if (!isPhone()) storeWidth(width.value)
}

const resizeStart = ref<{ x: number; width: number } | null>(null)
function onResizePointerDown (event: PointerEvent) {
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  resizeStart.value = { x: event.clientX, width: width.value }
}

function onResizePointerMove (event: PointerEvent) {
  if (!resizeStart.value) return
  width.value = clampWidth(resizeStart.value.width + event.clientX - resizeStart.value.x)
}

function onResizePointerUp () {
  if (!resizeStart.value) return
  resizeStart.value = null
  if (!isPhone()) storeWidth(width.value)
}

let resizeObserver: ResizeObserver | null = null
onMounted(() => {
  width.value = clampWidth(width.value)
  if (!viewport.value) return
  resizeObserver = new ResizeObserver(() => {
    viewportWidth.value = viewport.value?.clientWidth ?? 0
    onViewportScroll()
  })
  resizeObserver.observe(viewport.value)
})
onBeforeUnmount(() => resizeObserver?.disconnect())
</script>

<style scoped>
/* The width is set inline (resizable). */
.span-gutter-column {
  flex: none;
  position: relative;
  display: flex;
  flex-direction: column;
  background: #f8fafc;
  border-right: 1px solid #e2e8f0;
}

/* Straddles the right border. */
.span-gutter-resizer {
  position: absolute;
  top: 0;
  bottom: 0;
  right: -5px;
  width: 10px;
  z-index: 3;
  cursor: col-resize;
  touch-action: none;
}

.span-gutter-resizer::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 4px;
  width: 2px;
  background: transparent;
  transition: background 0.15s;
}

.span-gutter-resizer:hover::after,
.span-gutter-resizer:focus-visible::after,
.span-gutter-resizer.is-dragging::after {
  background: #94a3b8;
}

.span-gutter-resizer:focus-visible {
  outline: none;
}

/* `direction: rtl` starts the sideways scroll at the text side. `overflow: hidden` keeps
   the wheel, swipes and Shift+wheel from scrolling it sideways (they scroll the
   document); only .span-gutter-scrollbar does, through scrollLeft. */
.span-gutter-wrapper {
  position: relative;
  overflow: hidden;
  direction: rtl;
}

/* At the top of the gutter, over the padding above the first line, so the markers keep
   their offsets. While the document scrolls it sticks just below the reader toolbar
   (ReaderToolbar.vue, sticky at 96px, 36px tall), which floats over this side of the
   gutter. Sticking needs every ancestor up to the scrolling one to be free of
   `overflow: hidden`. */
.span-gutter-scrollbar {
  position: sticky;
  top: 138px;
  z-index: 2;
  height: 20px;
  margin-bottom: -20px;
  background: #f1f5f9;
  border-bottom: 1px solid #e2e8f0;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
  cursor: pointer;
}

.span-gutter-thumb {
  position: absolute;
  top: 3px;
  bottom: 3px;
  border-radius: 7px;
  background: rgba(15, 23, 42, 0.3);
  cursor: grab;
  touch-action: none;
}

.span-gutter-thumb:hover,
.span-gutter-thumb:active {
  background: rgba(15, 23, 42, 0.45);
}

.span-gutter {
  direction: ltr;
  position: relative;
  min-width: 100%;
}

/* From the span's first line to its last: fixed width, shorthand centred; a long
   shorthand is cut off. */
.gutter-item {
  position: absolute;
  width: 44px;
  min-height: 22px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  line-height: 19px;
  padding: 0 5px;
  border: 1.5px solid var(--tag-color);
  border-radius: 6px;
  background-color: var(--tag-color);
  color: #fff;
  white-space: nowrap;
  cursor: pointer;
  transition: opacity 0.15s, box-shadow 0.15s;
}

.gutter-icon {
  flex: none;
  height: 19px;
  opacity: 0.9;
}

.gutter-shorthand {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.gutter-item:hover,
.gutter-item.is-active {
  box-shadow: 0 0 0 2px #f8fafc, 0 0 0 4px color-mix(in srgb, var(--tag-color) 55%, transparent);
}

/* ── AI suggestions: the tag colour, dashed. ── */
.gutter-item.is-auto {
  background-color: #fff;
  color: var(--tag-color);
  border-style: dashed;
}

/* Two-way highlight with the AI suggestions panel: when a card is selected in the panel,
   ring its marker. The same class is added when the user clicks an auto span in the
   text or gutter so the panel mirrors the choice. */
.gutter-item.is-highlighted {
  box-shadow: 0 0 0 2px #f8fafc, 0 0 0 4px var(--tag-color);
}
</style>
