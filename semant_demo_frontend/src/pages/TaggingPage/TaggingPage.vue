<template>
  <q-page class="q-pa-md">
    <div class="row justify-center q-mb-md">
      <span class="text-h5">Text Tagging</span>
    </div>

    <div class="row q-col-gutter-lg">
      <!-- Text Container Panel -->
      <div class="col-12 col-md-8">
        <q-card>
          <q-card-section>
            <div class="text-subtitle2 text-grey-7 q-mb-sm">
              Highlight text to select, or click an existing tag to edit. Drag
              the handles to adjust.
            </div>

            <div
              ref="textContainer"
              class="text-container"
              :class="{ 'is-dragging': draggingHandle }"
              @mouseup="handleMouseUp"
            >
              <span
                v-for="(seg, idx) in renderedSegments"
                :key="idx"
                :data-start="seg.start"
                :data-end="seg.end"
                :style="getSegmentStyle(seg)"
                class="text-segment"
                @click="handleSegmentClick(seg)"
                ><span
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
                ></span
                ><q-tooltip
                  v-if="seg.tags.length > 0 && !currentSelection?.editingId"
                >
                  <div v-for="tag in seg.tags" :key="tag.tagId">
                    {{ getTagName(tag.tagId) }}
                  </div>
                </q-tooltip>
              </span>
            </div>
          </q-card-section>
        </q-card>
      </div>

      <!-- Tagging & Adjustments Panel -->
      <div class="col-12 col-md-4">
        <q-card v-if="currentSelection" class="bg-blue-grey-1">
          <q-card-section>
            <div class="text-h6">
              {{ currentSelection.editingId ? 'Edit Tag' : 'New Selection' }}
            </div>

            <div class="q-mt-md hidden">
              <div class="row items-center q-gutter-x-sm q-mb-md">
                <span style="width: 50px" class="text-weight-bold">Start:</span>
                <q-badge color="primary" class="text-subtitle1 q-px-md">{{
                  currentSelection.start
                }}</q-badge>
              </div>
              <div class="row items-center q-gutter-x-sm">
                <span style="width: 50px" class="text-weight-bold">End:</span>
                <q-badge color="primary" class="text-subtitle1 q-px-md">{{
                  currentSelection.end
                }}</q-badge>
              </div>
            </div>
          </q-card-section>

          <q-separator />

          <q-card-section>
            <div class="text-subtitle1 text-weight-bold q-mb-sm">
              {{ currentSelection.editingId ? 'Tag Type' : 'Assign Tag' }}
            </div>
            <div class="row q-gutter-sm">
              <q-btn
                v-for="tag in availableTags"
                :key="tag.tagUuid"
                :label="tag.tagName"
                :icon="tag.tagPictogram"
                :disable="isProcessing"
                :style="{
                  backgroundColor: tag.tagColor,
                  color: '#fff',
                  opacity:
                    currentSelection.editingId &&
                    currentSelection.tagId !== tag.tagUuid
                      ? 0.4
                      : 1
                }"
                @click="handleTagClick(tag.tagUuid)"
              >
                <q-icon
                  v-if="
                    currentSelection.editingId &&
                    currentSelection.tagId === tag.tagUuid
                  "
                  name="check"
                  class="q-ml-xs"
                />
              </q-btn>
            </div>
          </q-card-section>

          <q-card-actions
            class="q-pa-md bg-grey-3 row justify-between items-center"
          >
            <q-btn
              v-if="currentSelection.editingId"
              flat
              icon="delete"
              label="Remove Tag"
              color="negative"
              :loading="isProcessing"
              @click="deleteEditedTag"
            />
            <div v-else></div>

            <div class="row q-gutter-sm">
              <q-btn
                flat
                label="Cancel"
                color="grey-8"
                @click="clearSelection"
                :disable="isProcessing"
              />
              <q-btn
                v-if="currentSelection.editingId"
                label="Save Changes"
                color="primary"
                :loading="isProcessing"
                @click="saveEditedTag"
              />
            </div>
          </q-card-actions>
        </q-card>

        <!-- Default Empty State -->
        <q-card v-else class="bg-grey-2">
          <q-card-section class="text-center text-grey-7 q-py-xl">
            <q-icon name="edit_note" size="48px" class="q-mb-sm" />
            <div>Select text or click an existing tag.</div>
          </q-card-section>
        </q-card>
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useTagging } from './composables/useTagging'
import { TagSpan } from 'src/generated/api'
import { snapToWordBoundary } from './utils'

// --- Types ---
interface RenderSegment {
  text: string
  tags: TagSpan[]
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
}

// --- State ---
const currentSelection = ref<SelectionState | null>(null)
const textContainer = ref<HTMLElement | null>(null)

const snapToWords = true

const draggingHandle = ref<'start' | 'end' | null>(null)
let justFinishedDrag = false

const {
  chunk,
  tagSpans,
  isProcessing,
  getChunk,
  getTagSpans,
  createTagSpan,
  updateTagSpan,
  deleteTagSpan
} = useTagging()

const availableTags = ref([
  {
    tagName: 'Reproduktory',
    tagShorthand: 'repr',
    tagColor: '#e91e63',
    tagPictogram: 'square',
    tagDefinition: 'Reproduktory je věc, která produkuje zvuk',
    tagExamples: ['repráky'],
    collectionName: 'repraky_collection',
    tagUuid: '01f490ee-5b1b-46b4-b0e9-73476fa9c123'
  },
  {
    tagName: 'Prezident',
    tagShorthand: 'p',
    tagColor: '#4caf50',
    tagPictogram: 'circle',
    tagDefinition: 'Hlava statu',
    tagExamples: ['EU Cesko'],
    collectionName: 'MojeKolekce',
    tagUuid: '025a38bf-81cf-41c3-aa10-74e24f362bb9'
  }
])

// --- Segment Builder Logic ---
const renderedSegments = computed(() => {
  if (!chunk.value?.text) return []
  const text = chunk.value.text
  const segments: RenderSegment[] = []

  let currentTagsStr = ''
  let currentIsSelected = false
  let currentSeg: RenderSegment | null = null

  for (let i = 0; i < text.length; i++) {
    const char = text[i]

    const activeTags = tagSpans.value.filter(
      (t) =>
        i >= t.start && i < t.end && t.id !== currentSelection.value?.editingId
    )

    activeTags.sort((a, b) => a.tagId.localeCompare(b.tagId))
    const tagsStr = activeTags.map((t) => t.tagId).join(',')

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
          currentSeg.start === currentSelection.value?.start
        currentSeg.isSelectionEnd =
          currentSeg.isSelected &&
          currentSeg.end === currentSelection.value?.end
        segments.push(currentSeg)
      }
      currentSeg = {
        text: char,
        tags: activeTags,
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
      currentSeg.start === currentSelection.value?.start
    currentSeg.isSelectionEnd =
      currentSeg.isSelected && currentSeg.end === currentSelection.value?.end
    segments.push(currentSeg)
  }
  return segments
})

// --- DOM Index Resolution Helper ---
// Maps any arbitrary DOM node and its offset perfectly back to your raw string index based on `data-start`
const getAbsoluteIndex = (node: Node | null, offset: number): number | null => {
  if (!node) return null

  if (node.nodeType === Node.TEXT_NODE) {
    const parent = node.parentElement
    const segment = parent?.closest('.text-segment')

    if (segment) {
      const start = parseInt(segment.getAttribute('data-start') || '0', 10)

      // If the node is the main text segment itself
      if (parent === segment) {
        return start + offset
      }
      // If they dragged onto the end handle
      if (parent?.classList.contains('handle-end')) {
        return parseInt(segment.getAttribute('data-end') || '0', 10)
      }
      return start
    }
  } else if (node.nodeType === Node.ELEMENT_NODE) {
    const el = node as HTMLElement

    // Fallback: If they clicked entirely outside segments but within container
    if (el.classList.contains('text-container')) {
      const child = el.childNodes[offset] as HTMLElement | undefined
      if (
        child &&
        child.nodeType === Node.ELEMENT_NODE &&
        child.hasAttribute('data-start')
      ) {
        return parseInt(child.getAttribute('data-start') || '0', 10)
      } else if (offset > 0) {
        const prev = el.childNodes[offset - 1] as HTMLElement | undefined
        if (
          prev &&
          prev.nodeType === Node.ELEMENT_NODE &&
          prev.hasAttribute('data-end')
        ) {
          return parseInt(prev.getAttribute('data-end') || '0', 10)
        }
      }
    }

    // Fallback: Clicked directly on a segment wrapper or handle span
    const segment = el.closest('.text-segment')
    if (segment) {
      if (el.classList.contains('handle-end')) {
        return parseInt(segment.getAttribute('data-end') || '0', 10)
      }
      return parseInt(segment.getAttribute('data-start') || '0', 10)
    }
  }
  return null
}

// --- Native Selection Handler ---
const handleMouseUp = () => {
  if (isProcessing.value || justFinishedDrag || draggingHandle.value) return

  const sel = window.getSelection()
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return

  const range = sel.getRangeAt(0)

  // Instantly grab precision boundaries safely
  let start = getAbsoluteIndex(range.startContainer, range.startOffset)
  let end = getAbsoluteIndex(range.endContainer, range.endOffset)

  if (start === null || end === null) return

  if (start > end) [start, end] = [end, start]

  if (snapToWords) {
    if (chunk.value?.text) {
      start = snapToWordBoundary(start, 'start', chunk.value.text)
      end = snapToWordBoundary(end, 'end', chunk.value.text)
    }
  }

  currentSelection.value = { start, end }
  sel.removeAllRanges()
}

// --- Drag Handle Logic (Mouse & Touch) ---
const startDrag = (e: MouseEvent | TouchEvent, type: 'start' | 'end') => {
  draggingHandle.value = type

  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
  document.addEventListener('touchmove', onDrag, { passive: false })
  document.addEventListener('touchend', stopDrag)
}

const onDrag = (e: MouseEvent | TouchEvent) => {
  if (!draggingHandle.value || !currentSelection.value || !chunk.value?.text)
    return

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

  let range = null

  // Standard (Blink/Webkit)
  if (typeof document.caretRangeFromPoint !== 'undefined') {
    range = document.caretRangeFromPoint(clientX, clientY)
  }

  // Firefox Fallback
  if (typeof (document as any).caretPositionFromPoint !== 'undefined') {
    const pos = (document as any).caretPositionFromPoint(clientX, clientY)
    if (pos && pos.offsetNode) {
      range = document.createRange()
      range.setStart(pos.offsetNode, pos.offset)
    }
  }

  if (!range) return

  let newIndex = getAbsoluteIndex(range.startContainer, range.startOffset)
  if (newIndex === null) return

  if (snapToWords) {
    newIndex = snapToWordBoundary(
      newIndex,
      draggingHandle.value,
      chunk.value.text
    )

    if (draggingHandle.value === 'start') {
      if (newIndex < currentSelection.value.end) {
        currentSelection.value.start = newIndex
      }
    } else {
      if (newIndex > currentSelection.value.start) {
        currentSelection.value.end = newIndex
      }
    }
  } else {
    const newIndex = getAbsoluteIndex(range.startContainer, range.startOffset)
    if (newIndex === null) return

    if (draggingHandle.value === 'start') {
      if (newIndex < currentSelection.value.end) {
        currentSelection.value.start = newIndex
      }
    } else {
      if (newIndex > currentSelection.value.start) {
        currentSelection.value.end = newIndex
      }
    }
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

// --- Click Handlers & Display ---
const handleSegmentClick = (seg: RenderSegment) => {
  if (currentSelection.value !== null || isProcessing.value || justFinishedDrag)
    return

  if (seg.tags.length > 0) {
    const tagToEdit = seg.tags[0]
    currentSelection.value = {
      start: tagToEdit.start,
      end: tagToEdit.end,
      editingId: tagToEdit.id as string | undefined,
      tagId: tagToEdit.tagId
    }
  }
}

const handleTagClick = async (tagId: string) => {
  if (!currentSelection.value || !chunk.value?.id) return

  if (currentSelection.value.editingId) {
    currentSelection.value.tagId = tagId
  } else {
    isProcessing.value = true
    await createTagSpan({
      span: {
        tagId,
        chunkId: chunk.value.id!,
        start: currentSelection.value.start,
        end: currentSelection.value.end
      }
    })
    await getTagSpans(chunk.value.id!)
    clearSelection()
    isProcessing.value = false
  }
}

const saveEditedTag = async () => {
  if (
    !currentSelection.value ||
    !currentSelection.value.editingId ||
    !chunk.value?.id
  )
    return
  isProcessing.value = true
  await updateTagSpan({
    spanId: currentSelection.value.editingId,
    tagSpan: {
      tagId: currentSelection.value.tagId!,
      start: currentSelection.value.start,
      end: currentSelection.value.end
    }
  })
  await getTagSpans(chunk.value.id!)
  clearSelection()
  isProcessing.value = false
}

const deleteEditedTag = async () => {
  if (
    !currentSelection.value ||
    !currentSelection.value.editingId ||
    !chunk.value?.id
  )
    return
  isProcessing.value = true
  await deleteTagSpan(currentSelection.value.editingId)
  await getTagSpans(chunk.value.id!)
  clearSelection()
  isProcessing.value = false
}

const clearSelection = () => {
  currentSelection.value = null
}

const getTagName = (tagId: string) => {
  const tag = availableTags.value.find((t) => t.tagUuid === tagId)
  return tag ? tag.tagName : 'Unknown Tag'
}

const getSegmentStyle = (seg: RenderSegment) => {
  if (seg.isSelected) {
    if (currentSelection.value?.tagId) {
      const draftTag = availableTags.value.find(
        (t) => t.tagUuid === currentSelection.value!.tagId
      )
      if (draftTag)
        return {
          backgroundColor: draftTag.tagColor + '60',
          borderBottom: `2px solid ${draftTag.tagColor}`,
          color: '#000'
        }
    }
    return {
      backgroundColor: '#ffe082',
      borderBottom: '2px solid #ffca28',
      color: '#000'
    }
  }

  if (seg.tags.length > 0) {
    const tag = availableTags.value.find((t) => t.tagUuid === seg.tags[0].tagId)
    const color = tag ? tag.tagColor : '#cccccc'
    return {
      backgroundColor: color + '40',
      borderBottom: `2px solid ${color}`,
      cursor: 'pointer'
    }
  }
  return {}
}

const getHandleStyle = () => {
  let color = '#1976d2'
  if (currentSelection.value?.tagId) {
    const draftTag = availableTags.value.find(
      (t) => t.tagUuid === currentSelection.value!.tagId
    )
    if (draftTag) color = draftTag.tagColor
  }
  return { '--handle-color': color }
}

onMounted(async () => {
  await getChunk()
  if (chunk.value?.id) await getTagSpans(chunk.value.id)
})
</script>

<style scoped>
.text-container {
  white-space: pre-wrap;
  font-size: 16px;
  line-height: 1.8;
  padding: 16px;
  border: 1px solid #e0e0e0;
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

/* Base style for Native-feeling Drag Handles */
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

/* Dots at top/bottom mimicking iOS/Android selections */
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
  user-select: none !important; /* Prevents native text-selection flashes */
}
</style>
