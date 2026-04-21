<template>
  <div class="chunk-annotator" :data-chunk-id="chunkId" :class="{ 'is-dragging': draggingHandle }">
    <span
      v-for="(segment, i) in renderedSegments"
      :key="i"
      class="text-segment"
      :class="{
        'is-tagged': segment.tags.length > 0,
        'is-selected': segment.isSelected,
        'is-auto': segment.isAuto,
        'is-highlighted': segment.isHighlighted
      }"
      :style="getSegmentStyle(segment)"
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
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onBeforeUnmount } from 'vue'
import type { ProjectedSpan, LocalSelection } from 'src/composables/useAnnotations'
import type { Tag } from 'src/models/tags'

interface TextSegment {
  text: string
  start: number
  end: number
  tags: ProjectedSpan[]
  isSelected: boolean
  isAuto: boolean
  isHighlighted: boolean
  isSelectionStart: boolean
  isSelectionEnd: boolean
}

const props = defineProps<{
  chunkId: string
  text: string
  spans: ProjectedSpan[]
  selection: LocalSelection | null
  availableTags: Tag[]
  highlightSpanId?: string | null
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
  return '#f59e0b'
})

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

    segments.push({
      text: text.slice(start, end),
      start,
      end,
      tags: activeTags,
      isSelected,
      isAuto,
      isHighlighted,
      isSelectionStart: isSelected && start === props.selection?.start && (props.selection?.showStartHandle ?? true),
      isSelectionEnd: isSelected && end === props.selection?.end && (props.selection?.showEndHandle ?? true)
    })
  }

  return segments
})

// ── Drag handles ──

const getCaretPoint = (clientX: number, clientY: number): { node: Node; offset: number } | null => {
  if (typeof document.caretPositionFromPoint === 'function') {
    const pos = document.caretPositionFromPoint(clientX, clientY)
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

  const chunkId = segmentEl.closest<HTMLElement>('[data-chunk-id]')?.dataset.chunkId
  if (!chunkId) return null

  const segStart = Number(segmentEl.dataset.start ?? '0')
  const segEnd = Number(segmentEl.dataset.end ?? segStart)
  if (!Number.isFinite(segStart) || !Number.isFinite(segEnd)) return null

  const rawOffset = node.nodeType === Node.TEXT_NODE ? segStart + offset : segStart
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

const getSegmentStyle = (segment: TextSegment) => {
  const style: Record<string, string> = {}

  if (segment.isSelected) {
    if (props.selection?.editingSpanId) {
      // Editing existing span — use the currently selected tag color (from toolbar)
      const color = props.selection.tagId
        ? (tagColorMap.value[props.selection.tagId] || '#3b82f6')
        : (segment.tags.length > 0 ? tagColorMap.value[segment.tags[0].tagId] || '#3b82f6' : '#3b82f6')
      style.backgroundColor = hexToRgba(color, 0.35)
    } else {
      // New selection — always yellow
      style.backgroundColor = '#ffe082'
    }
  } else if (segment.isHighlighted && segment.tags.length > 0) {
    // Find the hovered span's tag color specifically
    const hovered = segment.tags.find(t => t.id === props.highlightSpanId)
    const color = hovered
      ? (tagColorMap.value[hovered.tagId] || '#3b82f6')
      : (tagColorMap.value[segment.tags[0].tagId] || '#3b82f6')
    style.backgroundColor = hexToRgba(color, 0.25)
    style.borderBottom = segment.isAuto ? `2px dashed ${color}` : `2px solid ${color}`
  } else if (segment.tags.length > 0) {
    // Stack underlines for each tag via layered background gradients
    const LINE_H = 2 // line thickness
    const GAP = 1 // gap between lines
    const step = LINE_H + GAP
    const totalH = segment.tags.length * LINE_H + (segment.tags.length - 1) * GAP
    const gradients = segment.tags.map((tag, i) => {
      const c = tagColorMap.value[tag.tagId] || '#3b82f6'
      const isDashed = tag.type === 'auto'
      const rgba = hexToRgba(c, isDashed ? 0.35 : 0.6)
      const top = i * step
      return `linear-gradient(${rgba}, ${rgba}) 0 calc(100% - ${totalH - top}px) / 100% ${LINE_H}px no-repeat`
    })
    style.background = gradients.join(', ')
    style.paddingBottom = `${totalH + 2}px`
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
  line-height: 2;
  cursor: text;
}

.text-segment {
  border-radius: 2px;
  transition: background-color 0.15s;
  position: relative;
}

.text-segment.is-tagged:hover {
  filter: brightness(0.92);
}

.text-segment.is-highlighted {
  transition: background-color 0.2s ease;
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
