<template>
  <div
    class="chunk-annotator"
    :data-chunk-id="chunkId"
    :class="{ 'is-dragging': draggingHandle, 'has-approximate-passage': activeApproximate }"
  >
    <template v-for="segment in renderedSegments" :key="`${segment.start}-${segment.end}`">
      <!-- Where text from another page begins: a label outside the text (not selected or copied). -->
      <span
        v-if="segment.pageBreak"
        class="page-break"
        :class="{ 'page-break--approximate': segment.pageBreak.approximate }"
        role="separator"
        :aria-label="segment.pageBreak.approximate ? `${segment.pageBreak.label} (approximate position)` : segment.pageBreak.label"
        :title="segment.pageBreak.approximate ? 'Approximate position of the page start' : undefined"
        :data-label="segment.pageBreak.label"
        :data-page-break="segment.pageBreak.pageId"
      /><span
      class="text-segment"
      :class="{
        'is-tagged': segment.tags.length > 0,
        'is-selected': segment.isSelected,
        'is-auto': segment.isAuto,
        'is-highlighted': segment.isHighlighted,
        'is-active-passage': segment.isActivePassage,
        'is-current-page': segment.isCurrentPage,
        'has-deep-stack': segment.hasDeepStack
      }"
      :style="segment.style"
      :data-start="segment.start"
      :data-end="segment.end"
    ><span
        v-if="segment.isSelectionStart"
        class="selection-handle handle-start"
        :style="{ '--handle-color': handleColor }"
        @mousedown.prevent.stop="startDrag($event, 'start')"
        @touchstart.prevent.stop="startDrag($event, 'start')"
      ></span>{{ segment.text }}<span
        v-if="segment.isSelectionEnd"
        class="selection-handle handle-end"
        :style="{ '--handle-color': handleColor }"
        @mousedown.prevent.stop="startDrag($event, 'end')"
        @touchstart.prevent.stop="startDrag($event, 'end')"
      ></span></span>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onBeforeUnmount } from 'vue'
import type { ProjectedSpan, LocalSelection } from './useAnnotations'
import type { Tag } from 'src/generated/api'
import { assignLanes } from './spanLanes'

export interface PageBreakMark {
  /** UTF-16 offset of the page's first character in the chunk. */
  offset: number
  pageId: string
  label: string
  approximate?: boolean
}

interface TextSegment {
  text: string
  start: number
  end: number
  tags: ProjectedSpan[]
  isSelected: boolean
  isAuto: boolean
  isHighlighted: boolean
  /** In the passage focused from outside the text (`activeRange`). */
  isActivePassage: boolean
  /** On the page shown in the scan viewer (`pageRange`). */
  isCurrentPage: boolean
  /** Text from another page begins here (`pageBreaks`). */
  pageBreak: PageBreakMark | null
  /** The underlines reach the next line of text, so the line gets extra space below. */
  hasDeepStack: boolean
  isSelectionStart: boolean
  isSelectionEnd: boolean
  style: Record<string, string>
}

// Underlines: a 2px line per span (3px for the highlighted one), one lane every 3px below
// the text. From DEEP_STACK lanes on they would touch the next line of text.
const LINE_H = 2
const LANE_STEP = 3
const DEEP_STACK = 4
const NEW_SELECTION_COLOR = '#d5dfec'
const NEW_SELECTION_HANDLE_COLOR = '#334155'
const FADED_LINE_ALPHA = 0.25

const props = defineProps<{
  chunkId: string
  text: string
  spans: ProjectedSpan[]
  selection: LocalSelection | null
  availableTags: Tag[]
  highlightSpanId?: string | null
  /** The tag focused in the tags panel: its spans are tinted, the other tags' lines fade. */
  focusTagId?: string | null
  /** The part of this chunk in the passage focused from outside the text, e.g. a citation. */
  activeRange?: { start: number, end: number } | null
  /** The active passage is placed approximately (e.g. from an OCR line that differs). */
  activeApproximate?: boolean
  /** The part of this chunk on the page shown in the scan viewer. */
  pageRange?: { start: number, end: number } | null
  /** Where text from another page begins in this chunk. */
  pageBreaks?: PageBreakMark[]
}>()

const emit = defineEmits<{
  boundaryDrag: [payload: { chunkId: string; handle: 'start' | 'end'; charOffset: number }]
}>()

const draggingHandle = ref<'start' | 'end' | null>(null)

const tagColorMap = computed(() => {
  const map: Record<string, string> = {}
  for (const tag of props.availableTags) {
    map[tag.id] = tag.color
  }
  return map
})

const handleColor = computed(() => {
  if (props.selection?.tagId) {
    return tagColorMap.value[props.selection.tagId] || '#3b82f6'
  }
  return NEW_SELECTION_HANDLE_COLOR
})

const laneBySpanId = computed(() => assignLanes(props.spans))

/**
 * Split the chunk text into segments where each segment has a consistent
 * set of overlapping tags and selection state.
 */
const renderedSegments = computed((): TextSegment[] => {
  const text = props.text
  if (!text.length) return []

  // Collect all boundary points
  const boundaries = new Set<number>([0, text.length])

  for (const span of props.spans) {
    boundaries.add(Math.max(0, span.start))
    boundaries.add(Math.min(text.length, span.end))
  }

  if (props.selection) {
    boundaries.add(Math.max(0, props.selection.start))
    boundaries.add(Math.min(text.length, props.selection.end))
  }

  const active = props.activeRange
  if (active) {
    boundaries.add(Math.max(0, active.start))
    boundaries.add(Math.min(text.length, active.end))
  }

  const page = props.pageRange
  if (page) {
    boundaries.add(Math.max(0, page.start))
    boundaries.add(Math.min(text.length, page.end))
  }
  const breaks = new Map<number, PageBreakMark>()
  for (const mark of props.pageBreaks ?? []) {
    if (mark.offset < 0 || mark.offset >= text.length) continue
    boundaries.add(mark.offset)
    if (!breaks.has(mark.offset)) breaks.set(mark.offset, mark)
  }

  const sorted = Array.from(boundaries).sort((a, b) => a - b)
  const segments: TextSegment[] = []

  for (let i = 0; i < sorted.length - 1; i++) {
    const start = sorted[i]
    const end = sorted[i + 1]
    if (start >= end) continue

    const activeTags = props.spans.filter(
      (span) => span.start <= start && span.end >= end
    )

    const isSelected = props.selection
      ? props.selection.start <= start && props.selection.end >= end
      : false

    const isAuto = activeTags.some((s) => s.type === 'auto')

    const isHighlighted = props.highlightSpanId
      ? activeTags.some(t => t.id === props.highlightSpanId)
      : false

    const style = computeSegmentStyle(isSelected, activeTags)
    segments.push({
      text: text.slice(start, end),
      start,
      end,
      tags: activeTags,
      isSelected,
      isAuto,
      isHighlighted,
      isActivePassage: !!active && active.start <= start && active.end >= end,
      isCurrentPage: !!page && page.start <= start && page.end >= end,
      pageBreak: breaks.get(start) ?? null,
      hasDeepStack: '--stack-height' in style,
      isSelectionStart: isSelected && start === props.selection?.start && (props.selection?.showStartHandle ?? true),
      isSelectionEnd: isSelected && end === props.selection?.end && (props.selection?.showEndHandle ?? true),
      style
    })
  }

  return segments
})

// ── Drag handles ──

const getCaretPoint = (clientX: number, clientY: number): { node: Node; offset: number } | null => {
  // Standard, but not yet in the TypeScript 5.5 DOM types.
  const doc = document as Document & {
    caretPositionFromPoint?: (x: number, y: number) => { offsetNode: Node, offset: number } | null
  }
  if (typeof doc.caretPositionFromPoint === 'function') {
    const pos = doc.caretPositionFromPoint(clientX, clientY)
    if (pos?.offsetNode) {
      return { node: pos.offsetNode, offset: pos.offset }
    }
  }

  // Safari fallback. Deprecated but still needed for browser compatibility.
  if (typeof document.caretRangeFromPoint === 'function') {
    const range = document.caretRangeFromPoint(clientX, clientY)
    if (range) {
      return { node: range.startContainer, offset: range.startOffset }
    }
  }

  return null
}

function resolveCharOffset(clientX: number, clientY: number): { chunkId: string; charOffset: number } | null {
  const caretPoint = getCaretPoint(clientX, clientY)
  if (!caretPoint) return null

  const { node, offset } = caretPoint
  const element = node instanceof HTMLElement ? node : node.parentElement

  const segmentEl = element?.closest<HTMLElement>('.text-segment[data-start][data-end]')
  if (!segmentEl) return null

  // caretPositionFromPoint/caretRangeFromPoint resolve to the *closest text
  // position in the whole document*, not necessarily anything actually
  // rendered under the cursor. While transiting the vertical gap between
  // lines (this component uses a tall line-height, so that gap is
  // sizeable), that "closest" position can land in a distant segment or
  // even a different chunk, which then gets committed as the new boundary
  // and balloons the selection. Cross-check against a real hit-test at the
  // same point — if it doesn't land on the same segment, the cursor isn't
  // actually over text right now, so skip this tick instead of committing
  // a jump; the boundary resumes updating once the cursor reaches real text.
  const hitSegmentEl = document.elementFromPoint(clientX, clientY)
    ?.closest<HTMLElement>('.text-segment[data-start][data-end]')
  if (hitSegmentEl !== segmentEl) return null

  const chunkId = segmentEl.closest<HTMLElement>('[data-chunk-id]')?.dataset.chunkId
  if (!chunkId) return null

  const segStart = Number(segmentEl.dataset.start ?? '0')
  const segEnd = Number(segmentEl.dataset.end ?? segStart)
  if (!Number.isFinite(segStart) || !Number.isFinite(segEnd)) return null

  // The browser's caret API doesn't always resolve to a text node — at
  // segment/line-wrap boundaries, over whitespace, and (critically) when
  // the cursor is right on top of the drag-handle <span> itself (an empty
  // element with no children of its own — very easy to hit, since that's
  // literally what's being dragged), it resolves to an element instead,
  // with `offset` as a child-node index rather than a character offset.
  // Summing *that node's own* children only works for handle-start (whose
  // fallback of "0 chars in" happens to equal segStart) — for handle-end,
  // hitting the empty handle span the same way must resolve near segEnd,
  // not segStart, since the handle sits after the text. So walk the
  // *segment's* children instead, accumulating text length of the ones
  // that precede the hit node (or the hit node's own offset, if the hit
  // node is a direct child of the segment).
  let charsBefore = 0
  if (node.nodeType === Node.TEXT_NODE && node.parentElement === segmentEl) {
    charsBefore = offset
  } else {
    for (const child of Array.from(segmentEl.childNodes)) {
      if (child === node || (child instanceof HTMLElement && node instanceof Node && child.contains(node))) {
        if (node.nodeType !== Node.TEXT_NODE) {
          const limit = Math.min(offset, node.childNodes.length)
          for (let i = 0; i < limit; i++) {
            charsBefore += node.childNodes[i].textContent?.length ?? 0
          }
        }
        break
      }
      charsBefore += child.textContent?.length ?? 0
    }
  }
  const rawOffset = segStart + charsBefore
  const charOffset = Math.max(segStart, Math.min(segEnd, rawOffset))

  return { chunkId, charOffset }
}

const startDrag = (_e: MouseEvent | TouchEvent, handle: 'start' | 'end') => {
  draggingHandle.value = handle
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
  document.addEventListener('touchmove', onDrag, { passive: false })
  document.addEventListener('touchend', stopDrag)
}

const onDrag = (e: MouseEvent | TouchEvent) => {
  if (!draggingHandle.value) return

  e.preventDefault()
  window.getSelection()?.removeAllRanges()

  let clientX: number, clientY: number
  if ('touches' in e) {
    clientX = e.touches[0].clientX
    clientY = e.touches[0].clientY
  } else {
    clientX = e.clientX
    clientY = e.clientY
  }

  const result = resolveCharOffset(clientX, clientY)
  if (!result) return

  emit('boundaryDrag', {
    chunkId: result.chunkId,
    handle: draggingHandle.value,
    charOffset: result.charOffset
  })
}

const stopDrag = () => {
  draggingHandle.value = null
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
  document.removeEventListener('touchmove', onDrag)
  document.removeEventListener('touchend', stopDrag)
}

onBeforeUnmount(() => {
  stopDrag()
})

const computeSegmentStyle = (isSelected: boolean, tags: ProjectedSpan[]) => {
  const style: Record<string, string> = {}
  const highlighted = tags.find(t => t.id === props.highlightSpanId)

  if (isSelected) {
    if (props.selection?.editingSpanId) {
      // Editing existing span — use the currently selected tag color (from toolbar)
      const color = props.selection.tagId
        ? (tagColorMap.value[props.selection.tagId] || '#3b82f6')
        : (tags.length > 0 ? tagColorMap.value[tags[0].tagId] || '#3b82f6' : '#3b82f6')
      style.backgroundColor = hexToRgba(color, 0.22)
    } else {
      // New selection — neutral, so it can't be mistaken for a tag colour
      style.backgroundColor = NEW_SELECTION_COLOR
    }
  } else if (highlighted) {
    const color = tagColorMap.value[highlighted.tagId] || '#3b82f6'
    style.backgroundColor = hexToRgba(color, highlighted.type === 'auto' ? 0.12 : 0.2)
  } else if (props.focusTagId && tags.some(t => t.tagId === props.focusTagId)) {
    style.backgroundColor = hexToRgba(tagColorMap.value[props.focusTagId] || '#3b82f6', 0.12)
  }

  if (tags.length > 0) {
    // One line per span in its own lane: solid for approved spans, dashed for AI
    // suggestions. Lane k starts 1 + k * LANE_STEP px below the text.
    const lanes = tags.map(tag => laneBySpanId.value.get(tag.id ?? '') ?? 0)
    const stackH = LANE_STEP * (Math.max(...lanes) + 1) + 1
    const images: string[] = []
    const sizes: string[] = []
    const positions: string[] = []
    tags.forEach((tag, i) => {
      const tagColor = tagColorMap.value[tag.tagId] || '#3b82f6'
      const c = props.focusTagId && tag.tagId !== props.focusTagId && tag !== highlighted
        ? hexToRgba(tagColor, FADED_LINE_ALPHA)
        : tagColor
      const lineH = tag === highlighted ? LINE_H + 1 : LINE_H
      images.push(tag.type === 'auto'
        ? `repeating-linear-gradient(90deg, ${c} 0 5px, transparent 5px 8px)`
        : `linear-gradient(${c}, ${c})`)
      sizes.push(`100% ${lineH}px`)
      positions.push(`0 calc(100% - ${stackH - 1 - LANE_STEP * lanes[i] - lineH}px)`)
    })
    style.backgroundImage = images.join(', ')
    style.backgroundSize = sizes.join(', ')
    style.backgroundPosition = positions.join(', ')
    style.backgroundRepeat = 'no-repeat'
    style.paddingBottom = `${stackH}px`
    if (Math.max(...lanes) + 1 >= DEEP_STACK) style['--stack-height'] = `${stackH}px`
  }

  return style
}

const hexToRgba = (hex: string, alpha: number): string => {
  const cleaned = hex.replace('#', '')
  const r = parseInt(cleaned.substring(0, 2), 16)
  const g = parseInt(cleaned.substring(2, 4), 16)
  const b = parseInt(cleaned.substring(4, 6), 16)
  if (isNaN(r) || isNaN(g) || isNaN(b)) return `rgba(59, 130, 246, ${alpha})`
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}
</script>

<style scoped>
.chunk-annotator {
  display: inline;
  line-height: 2;
  cursor: text;
}

.text-segment {
  border-radius: 2px;
  transition: background-color 0.15s;
  position: relative;
}

.text-segment.is-tagged {
  cursor: pointer;
}

/* Underlines that would reach the next line of text: a zero-width strut at both ends
   of the segment makes its line box taller below the text, so only this line gets the
   extra space. */
.text-segment.has-deep-stack::before,
.text-segment.has-deep-stack::after {
  content: '';
  display: inline-block;
  width: 0;
  height: calc(0.9em + var(--stack-height));
  vertical-align: text-top;
}

/* A tag's or the selection's background (inline style) takes precedence. */
.text-segment.is-active-passage {
  background-color: rgba(250, 204, 21, 0.3);
}

/* An approximate place: the same tint, marked as uncertain by a dashed underline. */
.chunk-annotator.has-approximate-passage .text-segment.is-active-passage {
  background-color: rgba(250, 204, 21, 0.18);
  text-decoration: underline dashed rgba(161, 98, 7, 0.7);
  text-underline-offset: 4px;
}

/* The page shown in the scan viewer: a faint tint under the other marks. */
.text-segment.is-current-page {
  box-shadow: inset 0 -1.2em 0 rgba(59, 130, 246, 0.07);
}

.page-break {
  display: inline-block;
  margin: 0 6px 0 0;
  padding: 0 6px;
  border: 1px solid rgba(71, 85, 105, 0.45);
  border-radius: 8px;
  font-size: 0.72rem;
  line-height: 1.5;
  color: rgba(51, 65, 85, 0.9);
  vertical-align: 0.15em;
  user-select: none;
  cursor: default;
}

.page-break::before {
  content: attr(data-label);
}

.page-break--approximate {
  border-style: dashed;
}

.page-break--approximate::before {
  content: '≈ ' attr(data-label);
}

.text-segment.is-highlighted {
  transition: background-color 0.2s ease;
}

.chunk-annotator.is-dragging .text-segment {
  transition: none;
}

/* Drag handles */
.selection-handle {
  display: inline-block;
  position: relative;
  width: 4px;
  height: 1.1em;
  background-color: var(--handle-color);
  cursor: ew-resize;
  vertical-align: text-bottom;
  margin: 0 -2px;
  z-index: 10;
}

.handle-start::before {
  content: '';
  position: absolute;
  top: -5px;
  left: -3px;
  width: 10px;
  height: 10px;
  background-color: var(--handle-color);
  border-radius: 50%;
}

.handle-end::after {
  content: '';
  position: absolute;
  bottom: -5px;
  left: -3px;
  width: 10px;
  height: 10px;
  background-color: var(--handle-color);
  border-radius: 50%;
}

.chunk-annotator.is-dragging,
.chunk-annotator.is-dragging * {
  cursor: ew-resize !important;
  user-select: none !important;
}
</style>
