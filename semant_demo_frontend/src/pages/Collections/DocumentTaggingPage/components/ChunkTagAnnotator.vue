<template>
  <div
    ref="textContainer"
    class="text-container"
    :class="{ 'is-dragging': draggingHandle }"
    @mouseup="handleMouseUp"
  >
    <span
      v-for="(seg, idx) in renderedSegments"
      :key="`${seg.start}-${seg.end}`"
      :data-chunk-id="chunkId"
      :data-start="seg.start"
      :data-end="seg.end"
      :data-span-ids="seg.spanIds.length ? seg.spanIds.join(' ') : undefined"
      :style="getSegmentStyle(seg, idx)"
      class="text-segment"
      @mouseenter="handleSegmentMouseEnter(seg)"
      @mouseleave="handleSegmentMouseLeave(seg)"
      @click="handleSegmentClick(seg)"
    >
      <span
        v-if="seg.isSelectionStart"
        class="selection-handle handle-start"
        :style="getHandleStyle()"
        @mousedown.prevent.stop="startDrag($event, 'start')"
        @touchstart.prevent.stop="startDrag($event, 'start')"
      ></span
      >{{ seg.text
      }}<span
        v-if="seg.isSelectionEnd"
        class="selection-handle handle-end"
        :style="getHandleStyle()"
        @mousedown.prevent.stop="startDrag($event, 'end')"
        @touchstart.prevent.stop="startDrag($event, 'end')"
      ></span>
      <!--<q-tooltip v-if="seg.tags.length > 0 && !currentSelection?.editingId">
        <div v-for="tag in seg.tags" :key="tag.tagId">
          {{ getTagName(tag.tagId) }}
        </div>
      </q-tooltip>-->
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { type TagSpan } from 'src/generated/api/models/TagSpan'
import { snapToWordBoundary } from '../utils'
import { SpanType } from 'src/generated/api/models/SpanType'

interface RenderSegment {
  text: string
  tags: TagSpan[]
  spanIds: string[]
  isSelected: boolean
  start: number
  end: number
  isSelectionStart?: boolean
  isSelectionEnd?: boolean
}

interface SelectionState {
  start: number
  end: number
  editingId?: string
  tagId?: string
  spanType?: TagSpan['type']
}

interface SelectionBoundary {
  chunkId: string
  index: number
}

export interface AvailableTag {
  tagName: string
  tagColor: string
  tagPictogram: string
  tagShorthand: string
  tagDefinition?: string
  tagExamples?: string[]
  tagUuid: string | null
}

interface SpanWithSourceMeta extends TagSpan {
  sourceStart?: number
  sourceEnd?: number
}

interface ExternalHoveredMarker {
  spanId: string | null
  tagId: string
  spanType?: TagSpan['type'] | null
}

const props = withDefaults(
  defineProps<{
    chunkId: string
    chunkText: string
    tagSpans: TagSpan[]
    availableTags: AvailableTag[]
    isProcessing: boolean
    snapToWords?: boolean
    selection?: SelectionState | null
    showSelectionStartHandle?: boolean
    showSelectionEndHandle?: boolean
    selectionStartBoundary?: SelectionBoundary | null
    selectionEndBoundary?: SelectionBoundary | null
    editingSpanId?: string | null
    externalHoveredMarker?: ExternalHoveredMarker | null
  }>(),
  {
    snapToWords: true,
    selection: null,
    showSelectionStartHandle: true,
    showSelectionEndHandle: true,
    selectionStartBoundary: null,
    selectionEndBoundary: null,
    editingSpanId: null,
    externalHoveredMarker: null
  }
)

const emit = defineEmits<{
  selectionChange: [
    payload: {
      chunkId: string
      selection: SelectionState | null
      startBoundary?: SelectionBoundary
      endBoundary?: SelectionBoundary
      source?: 'mouse' | 'drag'
      dragHandle?: 'start' | 'end'
    }
  ]
  selectionEnd: []
  spanHoverStart: [marker: ExternalHoveredMarker]
  spanHoverEnd: []
}>()

const currentSelection = ref<SelectionState | null>(null)
const textContainer = ref<HTMLElement | null>(null)
const draggingHandle = ref<'start' | 'end' | null>(null)
let justFinishedDrag = false

watch(
  () => props.selection,
  (nextSelection) => {
    if (!nextSelection) {
      currentSelection.value = null
      return
    }
    currentSelection.value = { ...nextSelection }
  },
  { immediate: true }
)

const emitSelection = (
  overrideChunkId?: string,
  overrideSelection?: SelectionState | null
) => {
  const selectionToEmit =
    overrideSelection === undefined ? currentSelection.value : overrideSelection

  emit('selectionChange', {
    chunkId: overrideChunkId || props.chunkId,
    selection: selectionToEmit ? { ...selectionToEmit } : null
  })
}

const emitBoundaries = (
  startBoundary: SelectionBoundary,
  endBoundary: SelectionBoundary,
  source: 'mouse' | 'drag',
  dragHandle?: 'start' | 'end'
) => {
  emit('selectionChange', {
    chunkId: props.chunkId,
    selection: null,
    startBoundary,
    endBoundary,
    source,
    dragHandle
  })
}

const renderedSegments = computed(() => {
  if (!props.chunkText) return []
  const text = props.chunkText
  const segments: RenderSegment[] = []

  let currentTagsStr = ''
  let currentIsSelected = false
  let currentSeg: RenderSegment | null = null

  for (let i = 0; i < text.length; i++) {
    const char = text[i]

    const activeTags = props.tagSpans.filter(
      (t) => i >= t.start && i < t.end && t.id !== props.editingSpanId
    )

    activeTags.sort((a, b) => {
      const aKey = a.id ?? `${a.tagId}-${a.start}-${a.end}`
      const bKey = b.id ?? `${b.tagId}-${b.start}-${b.end}`
      return aKey.localeCompare(bKey)
    })
    const spanIds = activeTags
      .map((t) => t.id)
      .filter((id): id is string => !!id)
    const tagsStr = activeTags
      .map((t) => t.id ?? `${t.tagId}-${t.start}-${t.end}`)
      .join(',')

    const isSelected =
      currentSelection.value !== null &&
      i >= currentSelection.value.start &&
      i < currentSelection.value.end

    if (
      !currentSeg ||
      tagsStr !== currentTagsStr ||
      isSelected !== currentIsSelected
    ) {
      if (currentSeg) {
        currentSeg.end = i
        currentSeg.isSelectionStart =
          currentSeg.isSelected &&
          props.showSelectionStartHandle &&
          currentSeg.start === currentSelection.value?.start
        currentSeg.isSelectionEnd =
          currentSeg.isSelected &&
          props.showSelectionEndHandle &&
          currentSeg.end === currentSelection.value?.end
        segments.push(currentSeg)
      }

      currentSeg = {
        text: char,
        tags: activeTags,
        spanIds,
        isSelected,
        start: i,
        end: i + 1
      }
      currentTagsStr = tagsStr
      currentIsSelected = isSelected
    } else {
      currentSeg.text += char
    }
  }

  if (currentSeg) {
    currentSeg.end = text.length
    currentSeg.isSelectionStart =
      currentSeg.isSelected &&
      props.showSelectionStartHandle &&
      currentSeg.start === currentSelection.value?.start
    currentSeg.isSelectionEnd =
      currentSeg.isSelected &&
      props.showSelectionEndHandle &&
      currentSeg.end === currentSelection.value?.end
    segments.push(currentSeg)
  }

  return segments
})

const getAbsoluteBoundary = (
  node: Node | null,
  offset: number
): SelectionBoundary | null => {
  if (!node) return null

  const parseBoundaryFromSegment = (
    segment: Element,
    index: number
  ): SelectionBoundary => {
    const chunkId = segment.getAttribute('data-chunk-id') || props.chunkId
    return {
      chunkId,
      index
    }
  }

  if (node.nodeType === Node.TEXT_NODE) {
    const parent = node.parentElement
    const segment = parent?.closest('.text-segment')

    if (segment) {
      const start = parseInt(segment.getAttribute('data-start') || '0', 10)
      if (parent === segment) {
        return parseBoundaryFromSegment(segment, start + offset)
      }
      if (parent?.classList.contains('handle-end')) {
        return parseBoundaryFromSegment(
          segment,
          parseInt(segment.getAttribute('data-end') || '0', 10)
        )
      }
      return parseBoundaryFromSegment(segment, start)
    }
  } else if (node.nodeType === Node.ELEMENT_NODE) {
    const el = node as HTMLElement

    if (el.classList.contains('text-container')) {
      const child = el.childNodes[offset] as HTMLElement | undefined
      if (
        child &&
        child.nodeType === Node.ELEMENT_NODE &&
        child.hasAttribute('data-start')
      ) {
        return parseBoundaryFromSegment(
          child,
          parseInt(child.getAttribute('data-start') || '0', 10)
        )
      } else if (offset > 0) {
        const prev = el.childNodes[offset - 1] as HTMLElement | undefined
        if (
          prev &&
          prev.nodeType === Node.ELEMENT_NODE &&
          prev.hasAttribute('data-end')
        ) {
          return parseBoundaryFromSegment(
            prev,
            parseInt(prev.getAttribute('data-end') || '0', 10)
          )
        }
      }
    }

    const segment = el.closest('.text-segment')
    if (segment) {
      if (el.classList.contains('handle-end')) {
        return parseBoundaryFromSegment(
          segment,
          parseInt(segment.getAttribute('data-end') || '0', 10)
        )
      }
      return parseBoundaryFromSegment(
        segment,
        parseInt(segment.getAttribute('data-start') || '0', 10)
      )
    }
  }
  return null
}

const getAbsoluteIndex = (node: Node | null, offset: number): number | null => {
  const boundary = getAbsoluteBoundary(node, offset)
  if (!boundary || boundary.chunkId !== props.chunkId) return null
  return boundary.index
}

const handleMouseUp = () => {
  if (props.isProcessing || justFinishedDrag || draggingHandle.value) return

  const sel = window.getSelection()
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return

  const range = sel.getRangeAt(0)

  const startBoundary = getAbsoluteBoundary(
    range.startContainer,
    range.startOffset
  )
  const endBoundary = getAbsoluteBoundary(range.endContainer, range.endOffset)

  if (!startBoundary || !endBoundary) return

  if (
    startBoundary.chunkId !== props.chunkId ||
    endBoundary.chunkId !== props.chunkId
  ) {
    currentSelection.value = null
    emitBoundaries(startBoundary, endBoundary, 'mouse')
    emit('selectionEnd')
    sel.removeAllRanges()
    return
  }

  let start = startBoundary.index
  let end = endBoundary.index

  if (start > end) [start, end] = [end, start]

  if (props.snapToWords) {
    start = snapToWordBoundary(start, 'start', props.chunkText)
    end = snapToWordBoundary(end, 'end', props.chunkText)
  }

  currentSelection.value = { start, end }
  emitSelection()
  emit('selectionEnd')
  sel.removeAllRanges()
}

const startDrag = (_e: MouseEvent | TouchEvent, type: 'start' | 'end') => {
  draggingHandle.value = type

  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
  document.addEventListener('touchmove', onDrag, { passive: false })
  document.addEventListener('touchend', stopDrag)
}

const onDrag = (e: MouseEvent | TouchEvent) => {
  if (!draggingHandle.value) return

  const hasGlobalBoundaries =
    !!props.selectionStartBoundary && !!props.selectionEndBoundary

  if (!hasGlobalBoundaries && (!currentSelection.value || !props.chunkText)) {
    return
  }

  e.preventDefault()
  window.getSelection()?.removeAllRanges()

  let clientX, clientY
  if ('touches' in e) {
    clientX = e.touches[0].clientX
    clientY = e.touches[0].clientY
  } else {
    clientX = e.clientX
    clientY = e.clientY
  }

  let range: Range | null = null

  if (typeof document.caretRangeFromPoint !== 'undefined') {
    range = document.caretRangeFromPoint(clientX, clientY)
  }

  if (typeof document.caretPositionFromPoint !== 'undefined') {
    const pos = document.caretPositionFromPoint(clientX, clientY)
    if (pos && pos.offsetNode) {
      range = document.createRange()
      range.setStart(pos.offsetNode, pos.offset)
    }
  }

  if (!range) return

  const boundaryAtCursor = getAbsoluteBoundary(
    range.startContainer,
    range.startOffset
  )
  if (!boundaryAtCursor) return

  if (props.selectionStartBoundary && props.selectionEndBoundary) {
    if (draggingHandle.value === 'start') {
      emitBoundaries(
        boundaryAtCursor,
        props.selectionEndBoundary,
        'drag',
        'start'
      )
    } else {
      emitBoundaries(
        props.selectionStartBoundary,
        boundaryAtCursor,
        'drag',
        'end'
      )
    }
    return
  }

  if (!currentSelection.value) return

  let newIndex = getAbsoluteIndex(range.startContainer, range.startOffset)
  if (newIndex === null) return

  if (props.snapToWords) {
    newIndex = snapToWordBoundary(
      newIndex,
      draggingHandle.value,
      props.chunkText
    )
  }

  if (draggingHandle.value === 'start') {
    if (newIndex < currentSelection.value.end) {
      currentSelection.value.start = newIndex
      emitSelection()
    }
  } else if (newIndex > currentSelection.value.start) {
    currentSelection.value.end = newIndex
    emitSelection()
  }
}

const stopDrag = () => {
  if (draggingHandle.value) {
    justFinishedDrag = true
    setTimeout(() => {
      justFinishedDrag = false
    }, 100)
    draggingHandle.value = null
    emit('selectionEnd')
  }
  draggingHandle.value = null

  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
  document.removeEventListener('touchmove', onDrag)
  document.removeEventListener('touchend', stopDrag)
}

const handleSegmentClick = (seg: RenderSegment) => {
  if (props.isProcessing || justFinishedDrag) return

  if (seg.tags.length > 0) {
    clearLocalHoverMarker()

    const tagToEdit = seg.tags[0] as SpanWithSourceMeta | undefined
    if (!tagToEdit) return

    const sourceChunkId = tagToEdit.chunkId || props.chunkId
    const sourceStart =
      sourceChunkId === props.chunkId
        ? tagToEdit.start
        : (tagToEdit.sourceStart ?? tagToEdit.start)
    const sourceEnd =
      sourceChunkId === props.chunkId
        ? tagToEdit.end
        : (tagToEdit.sourceEnd ?? tagToEdit.end)

    const nextSelection = {
      start: sourceStart,
      end: sourceEnd,
      editingId: tagToEdit.id as string | undefined,
      tagId: tagToEdit.tagId,
      spanType: tagToEdit.type
    }

    currentSelection.value =
      sourceChunkId === props.chunkId ? nextSelection : null
    emitSelection(sourceChunkId, nextSelection)
    emit('selectionEnd')
  }
}

const clearLocalHoverMarker = () => {
  emit('spanHoverEnd')
}

const resolvePrimaryHoveredMarker = (
  targetSeg: RenderSegment
): ExternalHoveredMarker | null => {
  if (!targetSeg.spanIds.length) return null
  const primaryHoveredTag = targetSeg.tags[0]
  if (!primaryHoveredTag?.id) return null

  return {
    spanId: primaryHoveredTag.id,
    tagId: primaryHoveredTag.tagId,
    spanType: primaryHoveredTag.type
  }
}

const handleSegmentMouseEnter = (seg: RenderSegment) => {
  if (currentSelection.value?.editingId) {
    clearLocalHoverMarker()
    return
  }

  const marker = resolvePrimaryHoveredMarker(seg)
  if (!marker) {
    clearLocalHoverMarker()
    return
  }

  emit('spanHoverStart', marker)
}

const handleSegmentMouseLeave = (seg: RenderSegment) => {
  if (currentSelection.value?.editingId) {
    clearLocalHoverMarker()
    return
  }

  if (!seg.spanIds.length) return
  clearLocalHoverMarker()
}

const getTagName = (tagId: string) => {
  const tag = props.availableTags.find((item) => item.tagUuid === tagId)
  return tag ? tag.tagName : 'Unknown Tag'
}

const getEffectiveHoveredMarker = (): ExternalHoveredMarker | null => {
  return props.externalHoveredMarker
}

const getTagColorStyle = (
  tagId: string | null | undefined,
  spanType: TagSpan['type'] | null | undefined,
  selected = false
) => {
  const tag = props.availableTags.find((item) => item.tagUuid === tagId)
  const color = tag?.tagColor || '#cccccc'

  if (selected) {
    return {
      backgroundColor: `${color}60`,
      borderColor: color,
      borderStyle: 'solid',
      color: '#000'
    }
  }

  if (spanType === SpanType.auto) {
    return {
      backgroundColor: `${color}24`,
      borderColor: color,
      borderStyle: 'dashed',
      cursor: 'pointer'
    }
  }

  return {
    backgroundColor: `${color}40`,
    borderColor: color,
    borderStyle: 'solid',
    cursor: 'pointer'
  }
}

const applyHoverVisualState = (
  seg: RenderSegment,
  baseStyle: Record<string, string | undefined>
) => {
  const effectiveHoveredMarker = getEffectiveHoveredMarker()
  const effectiveHoveredSpanIds = effectiveHoveredMarker?.spanId
    ? [effectiveHoveredMarker.spanId]
    : []
  const hoverIsActive =
    !currentSelection.value?.editingId && effectiveHoveredSpanIds.length > 0
  const isTaggedSegment = seg.spanIds.length > 0
  const isHoveredSpanSegment =
    hoverIsActive &&
    isTaggedSegment &&
    seg.spanIds.some((spanId) => effectiveHoveredSpanIds.includes(spanId))

  if (!hoverIsActive || !isTaggedSegment) {
    return baseStyle
  }

  if (!isHoveredSpanSegment) {
    return {
      ...baseStyle,
      opacity: '0.45'
    }
  }

  const hoveredColorStyle = getTagColorStyle(
    effectiveHoveredMarker?.tagId,
    effectiveHoveredMarker?.spanType
  )

  return {
    ...baseStyle,
    ...hoveredColorStyle,
    opacity: '1'
  }
}

const segmentHasOutline = (seg: RenderSegment) => {
  return seg.isSelected || seg.tags.length > 0
}

const mergeOutlineByNeighbors = (
  seg: RenderSegment,
  index: number,
  style: Record<string, string | undefined>
) => {
  if (!style.borderColor || !style.borderStyle) {
    return style
  }

  const prevSeg = renderedSegments.value[index - 1]
  const nextSeg = renderedSegments.value[index + 1]
  const prevHasOutline = !!prevSeg && segmentHasOutline(prevSeg)
  const nextHasOutline = !!nextSeg && segmentHasOutline(nextSeg)

  return {
    ...style,
    borderTopWidth: '2px',
    borderBottomWidth: '2px',
    borderLeftWidth: prevHasOutline ? '0px' : '2px',
    borderRightWidth: nextHasOutline ? '0px' : '2px'
  }
}

const getSegmentStyle = (seg: RenderSegment, index: number) => {
  if (seg.isSelected) {
    if (currentSelection.value?.tagId) {
      const selectedStyle = getTagColorStyle(
        currentSelection.value.tagId,
        currentSelection.value.spanType,
        true
      )
      const hoveredStyle = applyHoverVisualState(seg, selectedStyle)
      return mergeOutlineByNeighbors(seg, index, hoveredStyle)
    }

    const selectedStyle = {
      backgroundColor: '#ffe082',
      borderColor: '#ffca28',
      borderStyle: 'solid',
      color: '#000'
    }

    const hoveredStyle = applyHoverVisualState(seg, selectedStyle)
    return mergeOutlineByNeighbors(seg, index, hoveredStyle)
  }

  if (seg.tags.length > 0) {
    const taggedStyle = getTagColorStyle(seg.tags[0].tagId, seg.tags[0].type)
    const hoveredStyle = applyHoverVisualState(seg, taggedStyle)
    return mergeOutlineByNeighbors(seg, index, hoveredStyle)
  }

  return {}
}

const getHandleStyle = () => {
  let color = '#1976d2'
  if (currentSelection.value?.tagId) {
    const draftTag = props.availableTags.find(
      (tag) => tag.tagUuid === currentSelection.value?.tagId
    )
    if (draftTag) color = draftTag.tagColor
  }
  return { '--handle-color': color }
}
</script>

<style scoped>
.text-container {
  white-space: pre-wrap;
  font-size: 16px;
  line-height: 1.8;
  padding: 10px 16px 4px 16px;
  border-radius: 0 0 8px 8px;
  cursor: text;
  background-color: #fafafa;
}

.text-segment {
  transition:
    background-color 0.15s,
    border-color 0.15s,
    outline-color 0.15s;
  border-color: transparent;
  border-style: solid;
  border-width: 0;
  border-radius: 0;
  -webkit-box-decoration-break: clone;
  box-decoration-break: clone;
  padding: 4px 0px;
  margin: -3px 0;
}

.selection-handle {
  display: inline-block;
  position: relative;
  width: 4px;
  height: 24px;
  background-color: var(--handle-color);
  cursor: ew-resize;
  vertical-align: text-bottom;
  margin: 0 -2px;
  z-index: 10;
}

.handle-start::before {
  content: '';
  position: absolute;
  top: -6px;
  left: -3px;
  width: 10px;
  height: 10px;
  background-color: var(--handle-color);
  border-radius: 50%;
}

.handle-end::after {
  content: '';
  position: absolute;
  bottom: -9px;
  left: -3px;
  width: 10px;
  height: 10px;
  background-color: var(--handle-color);
  border-radius: 50%;
}

.text-container.is-dragging,
.text-container.is-dragging * {
  cursor: ew-resize !important;
  user-select: none !important;
}
</style>
