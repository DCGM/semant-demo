<template>
  <div
    ref="root"
    class="document-text"
    :class="{ 'document-text--preserve-whitespace': preserveWhitespace }"
    @mouseup="onMouseUp"
  >
    <template v-for="(group, gIndex) in paragraphs" :key="gIndex">
      <p>
        <template v-for="chunk in group.chunks" :key="chunk.id">
          <!-- Inline content before a chunk, e.g. a page-boundary marker. -->
          <slot name="before-chunk" :chunk="chunk" />
          <ChunkAnnotator
            :chunk-id="chunk.id"
            :text="chunk.text"
            :spans="annotation?.spansFor(chunk.id) ?? NO_SPANS"
            :selection="annotation?.selectionFor(chunk.id) ?? null"
            :available-tags="annotation?.tags ?? NO_TAGS"
            :highlight-span-id="annotation?.highlightSpanId ?? null"
            :focus-tag-id="annotation?.focusTagId ?? null"
            :active-range="activeByChunk[chunk.id] ?? null"
            :class="chunkClass?.(chunk)"
            @boundary-drag="emit('boundaryDrag', $event)"
          />
        </template>
      </p>
      <!-- Between paragraphs where chunks are missing from the text, e.g. load controls. -->
      <slot v-if="group.gapAfter !== null" name="gap" :paragraph="group" />
    </template>
  </div>
</template>

<script setup lang="ts" generic="T extends TextChunk">
import { computed, ref } from 'vue'
import type { Tag } from 'src/generated/api'
import ChunkAnnotator from 'src/features/annotations/ChunkAnnotator.vue'
import type { ProjectedSpan } from 'src/features/annotations/useAnnotations'
// TextChunk is the bound of the `generic` attribute, which the linter does not see.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import type { ChunkClass, TextChunk, TextPaneAnnotation, TextSelection } from './documentTextPane'
import { groupParagraphs, rangeByChunk, resolveSelectionEndpoint, type ChunkRange, type TextPoint } from './readerOffsets'

// The continuous canonical text of a document's chunks, in the given order: chunks
// grouped into paragraphs, their stored text unchanged, with the original whitespace
// by default. Positions in it are (chunk id, UTF-16 offset in the chunk's text), as
// annotation offsets are. The pane uses no store and makes no request: its owner loads
// the chunks, decides which are shown, and, for a collection, passes `annotation` and
// handles the selection.
const props = withDefaults(defineProps<{
  /** The chunks shown, in document order; a gap in `order` ends a paragraph. */
  chunks: T[]
  preserveWhitespace?: boolean
  annotation?: TextPaneAnnotation | null
  /** A passage focused from outside the text, highlighted; may continue into later chunks. */
  activeRange?: ChunkRange | null
  chunkClass?: ChunkClass<T>
}>(), {
  preserveWhitespace: true,
  annotation: null,
  activeRange: null,
  chunkClass: undefined
})

const emit = defineEmits<{
  /** Text was selected; the browser selection is left for the owner to keep or clear. */
  select: [selection: TextSelection, event: MouseEvent]
  /** A click without a selection; `point` is where the caret went, if in the text. */
  textClick: [point: TextPoint | null, event: MouseEvent]
  boundaryDrag: [payload: { chunkId: string; handle: 'start' | 'end'; charOffset: number }]
}>()

const NO_SPANS: ProjectedSpan[] = []
const NO_TAGS: Tag[] = []

const root = ref<HTMLElement | null>(null)
const paragraphs = computed(() => groupParagraphs(props.chunks))
const activeByChunk = computed(() => props.activeRange ? rangeByChunk(props.activeRange, props.chunks) : {})

/** A DOM position as a canonical text position, when it is in this pane's text. */
function pointAt (node: Node | null, offset: number): TextPoint | null {
  if (!node || !root.value?.contains(node)) return null
  return resolveSelectionEndpoint(node, offset)
}

function onMouseUp (e: MouseEvent) {
  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
    emit('textClick', selection?.rangeCount ? pointAt(selection.anchorNode, selection.anchorOffset) : null, e)
    return
  }
  const range = selection.getRangeAt(0)
  const start = pointAt(range.startContainer, range.startOffset)
  const end = pointAt(range.endContainer, range.endOffset)
  if (start && end) emit('select', { start, end }, e)
}

const chunkElement = (chunkId: string) =>
  Array.from(root.value?.querySelectorAll<HTMLElement>('[data-chunk-id]') ?? [])
    .find((el) => el.dataset.chunkId === chunkId) ?? null

function scrollToChunk (chunkId: string) {
  chunkElement(chunkId)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

function scrollToRange ({ chunkId, start, end }: ChunkRange) {
  const chunkEl = chunkElement(chunkId)
  if (!chunkEl) return
  for (const seg of Array.from(chunkEl.querySelectorAll<HTMLElement>('.text-segment'))) {
    const segStart = Number(seg.dataset.start)
    const segEnd = Number(seg.dataset.end)
    // The first segment the range reaches into.
    if (segEnd > start && segStart < Math.max(end, start + 1)) {
      seg.scrollIntoView({ behavior: 'smooth', block: 'center' })
      return
    }
  }
}

defineExpose({ root, scrollToChunk, scrollToRange })
</script>

<style scoped>
.document-text {
  max-width: none;
  margin: 0;
  font-size: 1.08rem;
  line-height: 2;
  color: rgba(15, 23, 42, 0.95);
}

.document-text p {
  margin: 0 0 18px;
}

/* Text exactly as stored (consecutive spaces and line breaks inside each chunk kept).
   Wrapping is still allowed so long lines don't overflow the column. */
.document-text--preserve-whitespace :deep(.text-segment) {
  white-space: pre-wrap;
}

/* A chunk's text has no line break at its end, so inline chunks would continue the
   previous chunk's last line, making each chunk's first line about twice as long.
   Each chunk starts on its own line instead. */
.document-text--preserve-whitespace :deep(.chunk-annotator) {
  display: block;
}

@media (max-width: 599px) {
  .document-text {
    font-size: 1rem;
    line-height: 1.9;
  }
}
</style>
