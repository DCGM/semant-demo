<template>
  <div
    ref="textContainer"
    class="text-container"
    :class="{ 'is-dragging': draggingHandle }"
    @mouseup="handleMouseUp"
  >
    <span
      v-for="seg in renderedSegments"
      :key="`${seg.start}-${seg.end}`"
      :data-chunk-id="chunkId"
      :data-start="seg.start"
      :data-end="seg.end"
      :data-span-ids="seg.spanIds.length ? seg.spanIds.join(' ') : undefined"
      :style="getSegmentStyle(seg)"
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
      <q-tooltip v-if="seg.tags.length > 0 && !currentSelection?.editingId">
        <div v-for="tag in seg.tags" :key="tag.tagId">
          {{ getTagName(tag.tagId) }}
        </div>
      </q-tooltip>
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
  tagUuid: string | null
}

interface SpanWithSourceMeta extends TagSpan {
  sourceStart?: number
  sourceEnd?: number
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
  }>(),
  {
    snapToWords: true,
    selection: null,
    showSelectionStartHandle: true,
    showSelectionEndHandle: true,
    selectionStartBoundary: null,
    selectionEndBoundary: null,
    editingSpanId: null
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
}>()

const currentSelection = ref<SelectionState | null>(null)
const textContainer = ref<HTMLElement | null>(null)
const draggingHandle = ref<'start' | 'end' | null>(null)
const hoveredSpanIds = ref<string[]>([])
const hoveredTagId = ref<string | null>(null)
const hoveredSpanType = ref<TagSpan['type'] | null>(null)
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
    overrideSelection === undefined
      ? currentSelection.value
      : overrideSelection

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
      (t) =>
        i >= t.start && i < t.end && t.id !== props.editingSpanId
    )

    activeTags.sort((a, b) => {
      const aKey = a.id ?? `${a.tagId}-${a.start}-${a.end}`
      const bKey = b.id ?? `${b.tagId}-${b.start}-${b.end}`
      return aKey.localeCompare(bKey)
    })
    const spanIds = activeTags.map((t) => t.id).filter((id): id is string => !!id)
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
  }
  draggingHandle.value = null

  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
  document.removeEventListener('touchmove', onDrag)
  document.removeEventListener('touchend', stopDrag)
}

const handleSegmentClick = (seg: RenderSegment) => {
  if (currentSelection.value !== null || props.isProcessing || justFinishedDrag)
    return

  if (seg.tags.length > 0) {
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
  }
}

const handleSegmentMouseEnter = (seg: RenderSegment) => {
  if (currentSelection.value?.editingId) {
    hoveredSpanIds.value = []
    hoveredTagId.value = null
    hoveredSpanType.value = null
    return
  }

  if (!seg.spanIds.length) {
    hoveredSpanIds.value = []
    hoveredTagId.value = null
    hoveredSpanType.value = null
    return
  }

  hoveredSpanIds.value = seg.spanIds

  const hoveredTag = seg.tags.find((tag) =>
    seg.spanIds.includes(tag.id as string)
  )
  hoveredTagId.value = hoveredTag?.tagId || seg.tags[0]?.tagId || null
  hoveredSpanType.value = hoveredTag?.type || seg.tags[0]?.type || null
}

const handleSegmentMouseLeave = (seg: RenderSegment) => {
  if (currentSelection.value?.editingId) {
    hoveredSpanIds.value = []
    hoveredTagId.value = null
    hoveredSpanType.value = null
    return
  }

  if (!seg.spanIds.length) return
  hoveredSpanIds.value = []
  hoveredTagId.value = null
  hoveredSpanType.value = null
}

const getTagName = (tagId: string) => {
  const tag = props.availableTags.find((item) => item.tagUuid === tagId)
  return tag ? tag.tagName : 'Unknown Tag'
}

const getSegmentStyle = (seg: RenderSegment) => {
  const hoverIsActive =
    !currentSelection.value?.editingId && hoveredSpanIds.value.length > 0
  const isTaggedSegment = seg.spanIds.length > 0
  const isHoveredSpanSegment =
    hoverIsActive &&
    isTaggedSegment &&
    seg.spanIds.some((spanId) => hoveredSpanIds.value.includes(spanId))
  const isDifferentSpanWhileHovering =
    hoverIsActive && isTaggedSegment && !isHoveredSpanSegment

  const getHoverOpacityStyle = () => {
    if (!hoverIsActive || !isTaggedSegment) return {}
    return {
      opacity: isHoveredSpanSegment ? '1' : '0.45'
    }
  }

  const getHoveredColorStyle = () => {
    if (!isHoveredSpanSegment || !hoveredTagId.value) return {}

    const hoveredTag = props.availableTags.find(
      (tag) => tag.tagUuid === hoveredTagId.value
    )
    const hoveredColor = hoveredTag?.tagColor || '#cccccc'

    if (hoveredSpanType.value === SpanType.auto) {
      return {
        backgroundColor: `${hoveredColor}24`,
        borderBottom: `2px dashed ${hoveredColor}`,
        color: '#000'
      }
    }

    return {
      backgroundColor: `${hoveredColor}40`,
      borderBottom: `2px solid ${hoveredColor}`,
      color: '#000'
    }
  }

  if (seg.isSelected) {
    if (currentSelection.value?.tagId) {
      const draftTag = props.availableTags.find(
        (tag) => tag.tagUuid === currentSelection.value?.tagId
      )
      if (draftTag) {
        const selectedStyle = {
          backgroundColor: `${draftTag.tagColor}60`,
          borderBottom: `2px solid ${draftTag.tagColor}`,
          color: '#000'
        }
        if (isDifferentSpanWhileHovering) {
          return {
            ...selectedStyle,
            opacity: '0.45'
          }
        }
        return {
          ...selectedStyle,
          ...getHoveredColorStyle(),
          ...getHoverOpacityStyle()
        }
      }
    }

    const selectedStyle = {
      backgroundColor: '#ffe082',
      borderBottom: '2px solid #ffca28',
      color: '#000'
    }
    if (isDifferentSpanWhileHovering) {
      return {
        ...selectedStyle,
        opacity: '0.45'
      }
    }

    return {
      ...selectedStyle,
      ...getHoveredColorStyle(),
      ...getHoverOpacityStyle()
    }
  }

  if (seg.tags.length > 0) {
    const tag = props.availableTags.find(
      (item) => item.tagUuid === seg.tags[0].tagId
    )
    const color = tag ? tag.tagColor : '#cccccc'

    if (seg.tags[0].type === SpanType.auto) {
      const autoStyle = {
        backgroundColor: `${color}24`,
        borderBottom: `2px dashed ${color}`,
        cursor: 'pointer'
      }
      if (isDifferentSpanWhileHovering) {
        return {
          ...autoStyle,
          opacity: '0.45'
        }
      }

      return {
        ...autoStyle,
        ...getHoveredColorStyle(),
        ...getHoverOpacityStyle()
      }
    }

    const taggedStyle = {
      backgroundColor: `${color}40`,
      borderBottom: `2px solid ${color}`,
      cursor: 'pointer'
    }
    if (isDifferentSpanWhileHovering) {
      return {
        ...taggedStyle,
        opacity: '0.45'
      }
    }

    return {
      ...taggedStyle,
      ...getHoveredColorStyle(),
      ...getHoverOpacityStyle()
    }
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
  padding: 16px;
  border-radius: 8px;
  cursor: text;
  background-color: #fafafa;
}

.text-segment {
  transition:
    background-color 0.15s,
    border-bottom 0.15s;
  border-bottom: 2px solid transparent;
  border-radius: 2px;
}

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
  bottom: -6px;
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
