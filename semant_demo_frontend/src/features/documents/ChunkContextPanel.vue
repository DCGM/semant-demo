<template>
  <div
    class="chunk-context column q-gutter-y-sm"
    :class="{ 'chunk-context--scroll-text': scrollText }"
    data-testid="chunk-context"
  >
    <div v-if="!targetChunkId" class="text-caption text-grey-7">
      {{ emptyText }}
    </div>

    <template v-else>
      <!-- Stays at the top of the sidebar's scroller while the text scrolls; with
           `scrollText`, above the text's own scroller. -->
      <div ref="headerEl" class="chunk-context__header" data-testid="chunk-context-header">
        <!-- What the passage is shown for (e.g. the open annotation), above its document. -->
        <slot name="header" />
        <div v-if="documentHeading" class="chunk-context__heading text-overline" data-testid="chunk-context-heading">
          {{ documentHeading }}
        </div>
        <div v-if="document" class="chunk-context__document">
          <!-- With `linkTitle`, the title itself opens the document (no separate button). -->
          <router-link
            v-if="linkTitle && openLink"
            :to="openLink"
            class="text-subtitle2 text-weight-medium chunk-context__title chunk-context__title--link"
            :title="`${documentTitle}. Open the whole document with its page scans`"
            :aria-label="`${documentTitle} (open the document)`"
            data-testid="chunk-context-title"
          >{{ documentTitle }}<q-icon name="open_in_new" size="1em" class="chunk-context__title-icon" /></router-link>
          <div
            v-else
            class="text-subtitle2 text-weight-medium chunk-context__title"
            :title="documentTitle"
            data-testid="chunk-context-title"
          >{{ documentTitle }}</div>
          <!-- The year and the link to the original on one line, wrapping on a phone. -->
          <div class="chunk-context__meta text-caption">
            <span class="text-grey-8">{{ document.yearIssued || 'Year N/A' }}</span>
            <OriginalSourceLink :document="document" :page-id="targetPageId" />
          </div>
        </div>
        <!-- The full document view (text and scans), unlike this passage beside the page. -->
        <q-btn
          v-if="openLink && !linkTitle"
          dense
          flat
          no-caps
          color="primary"
          icon="open_in_full"
          label="Open document"
          :to="openLink"
          class="chunk-context__open"
          title="Open the whole document with its page scans"
          data-testid="chunk-context-open"
        />
        <!-- Another passage of the same document is loading: the shown one stays (#493). -->
        <div
          v-if="loading && chunks.length"
          class="chunk-context__reloading"
          role="status"
          aria-label="Loading the passage"
          data-testid="chunk-context-reloading"
        >
          <q-spinner color="primary" size="1.25em" />
        </div>
        <q-btn
          v-if="returnLabel"
          dense
          flat
          no-caps
          color="primary"
          icon="center_focus_strong"
          :label="returnLabel"
          class="chunk-context__return"
          @click="emit('return')"
        />
      </div>

      <!-- The passage: laid out with the header (display: contents), or scrolled by itself. -->
      <div ref="bodyEl" class="chunk-context__body" data-testid="chunk-context-body" @scroll.passive="onBodyScroll">
        <!-- With `scrollText`: edge fades, shown only while there is more text in that direction. -->
        <div v-if="scrollText" class="chunk-context__fade-anchor chunk-context__fade-anchor--top" aria-hidden="true">
          <div class="chunk-context__fade" :class="{ 'chunk-context__fade--on': fadeTop }" data-testid="chunk-context-fade-top" :data-active="fadeTop" />
        </div>
        <!-- With `scrollText` and `backLabel`: a way back to the target when it is scrolled
             out of view, on the side where it is. Always present, so showing it moves nothing. -->
        <div v-if="scrollText && backLabel" class="chunk-context__back-anchor chunk-context__back-anchor--top">
          <q-btn
            v-show="targetAway === 'above'"
            rounded
            unelevated
            dense
            no-caps
            color="primary"
            icon="arrow_upward"
            :label="backLabel"
            class="chunk-context__back"
            data-testid="chunk-context-back"
            @click="emit('focus')"
          />
        </div>
        <div v-if="error" class="text-negative text-body2 row items-center q-gutter-x-sm" role="alert">
          <span>{{ error }}</span>
          <q-btn v-if="!chunks.length" dense flat no-caps color="primary" label="Retry" @click="emit('reload')" />
        </div>

        <div v-if="loading && !chunks.length" class="row items-center text-caption text-grey-7" aria-live="polite">
          <q-spinner color="primary" size="1.5em" class="q-mr-sm" />
          Loading the document…
        </div>

        <template v-else-if="chunks.length">
          <q-btn
            v-if="hasBefore"
            dense
            outline
            no-caps
            color="primary"
            icon="expand_less"
            label="Show earlier text"
            :loading="extending === 'before'"
            :disable="!!extending || loading"
            @click="emit('extend', 'before')"
          />
          <div v-else class="chunk-context__edge text-caption text-grey-6">Start of document</div>

          <div class="chunk-context__text">
            <section
              v-for="chunk in chunks"
              :key="chunk.id"
              :ref="el => setChunkEl(chunk.id, el as HTMLElement | null)"
              class="chunk-context__chunk"
              :class="{ 'chunk-context__chunk--target': chunk.id === targetChunkId }"
              :aria-current="chunk.id === targetChunkId ? 'true' : undefined"
              :aria-label="chunk.id === targetChunkId ? (targetLabel ? `Cited passage ${targetLabel}` : targetName) : undefined"
              :data-chunk-id="chunk.id"
            >
              <div
                v-if="targetLabel && chunk.id === targetChunkId"
                class="chunk-context__target-label text-caption text-weight-bold"
                data-testid="chunk-context-target-label"
              >{{ targetLabel }}</div>
              <div class="chunk-context__chunk-text text-body2" data-chunk-text><template
                v-for="(part, index) in textParts(chunk)"
                :key="index"
              ><mark
                v-if="part.marked"
                class="chunk-context__mark"
                :class="{ 'chunk-context__mark--pending': highlight?.pending }"
                data-testid="chunk-context-mark"
              >{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></div>
            </section>
          </div>

          <q-btn
            v-if="hasAfter"
            dense
            outline
            no-caps
            color="primary"
            icon="expand_more"
            label="Show later text"
            :loading="extending === 'after'"
            :disable="!!extending || loading"
            @click="emit('extend', 'after')"
          />
          <div v-else class="chunk-context__edge text-caption text-grey-6">End of document</div>
        </template>
        <div v-if="scrollText" class="chunk-context__fade-anchor chunk-context__fade-anchor--bottom" aria-hidden="true">
          <div class="chunk-context__fade" :class="{ 'chunk-context__fade--on': fadeBottom }" data-testid="chunk-context-fade-bottom" :data-active="fadeBottom" />
        </div>
        <div v-if="scrollText && backLabel" class="chunk-context__back-anchor chunk-context__back-anchor--bottom">
          <q-btn
            v-show="targetAway === 'below'"
            rounded
            unelevated
            dense
            no-caps
            color="primary"
            icon="arrow_downward"
            :label="backLabel"
            class="chunk-context__back"
            data-testid="chunk-context-back"
            @click="emit('focus')"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { QBtn, QIcon, QSpinner } from 'quasar'
import type { RouteLocationRaw } from 'vue-router'
import type { Document, DocumentChunk } from 'src/generated/api'
import OriginalSourceLink from './OriginalSourceLink.vue'
import type { ContextDirection } from './useChunkContext'
import { projectSpan } from 'src/features/annotations/spanOffsets'
import { scrollToTarget } from './contextScroll'

/** An exact range to mark: UTF-16 offsets on the chunk where it starts, possibly continuing
 * into the following chunks (span coordinates, `annotations/spanOffsets.ts`). */
export interface ContextHighlight {
  chunkId: string
  start: number
  end: number
  /** A range being edited, not saved yet: marked differently. */
  pending?: boolean
}

/** A point of the shown text: an offset (UTF-16) in a chunk's text. */
export interface ContextTextPoint {
  chunkId: string
  offset: number
}

const props = withDefaults(defineProps<{
  /** The chunk to highlight; null shows `emptyText`. */
  targetChunkId: string | null
  document: Document | null
  /** The loaded passage, in document order. */
  chunks: DocumentChunk[]
  hasBefore?: boolean
  hasAfter?: boolean
  /** Changes with every request to show the target (also the same one again): it is
   * scrolled into view as soon as it is loaded. */
  focusRequest?: number
  loading?: boolean
  extending?: ContextDirection | null
  error?: string | null
  /** Label of the action returning to where the target came from (e.g. a search result). */
  returnLabel?: string | null
  /** Reference shown with the highlighted target (e.g. a chat citation's `S3`); none by default. */
  targetLabel?: string | null
  /** Accessible name of the target chunk when it has no `targetLabel`. */
  targetName?: string
  /** A range marked in the text (an annotation); none by default. */
  highlight?: ContextHighlight | null
  /** The full document view at the target (#545, workspace/documentLink.ts); no link by default. */
  openLink?: RouteLocationRaw | null
  /** The passage scrolls by itself below a header that stays in place, instead of the
   * sidebar scrolling both; needs a definite height (`RightSidebarPanel` `fill`). */
  scrollText?: boolean
  /** With `openLink`: the document title is the link to it, instead of an *Open document* button. */
  linkTitle?: boolean
  /** With `scrollText`: the label of the way back to the target when it is scrolled out of view. */
  backLabel?: string | null
  /** Heading above the document title, separating it from the `header` slot; none by default. */
  documentHeading?: string | null
  emptyText?: string
  /** Whether the panel can be seen now (e.g. its sidebar tab is active and open): a request
   * to show the target waits until it is, as scrolling hidden content does nothing. */
  visible?: boolean
}>(), {
  hasBefore: false,
  hasAfter: false,
  focusRequest: 0,
  loading: false,
  extending: null,
  error: null,
  returnLabel: null,
  targetLabel: null,
  targetName: 'Matched passage',
  highlight: null,
  openLink: null,
  documentHeading: null,
  scrollText: false,
  linkTitle: false,
  backLabel: null,
  emptyText: 'Nothing selected.',
  visible: true
})

const emit = defineEmits<{
  extend: [direction: ContextDirection]
  /** Load the passage around the target again (retry). */
  reload: []
  return: []
  /** Bring the target into view again (it was scrolled away or dropped by extending). */
  focus: []
}>()

const targetLoaded = computed(() => props.chunks.some(c => c.id === props.targetChunkId))
// The original opens at the matched passage's first page. Remembered once the target is
// loaded: extending the passage can trim the target chunk away, not the page it is on.
const targetPageId = ref<string | null>(null)
watch(() => props.targetChunkId, () => { targetPageId.value = null })
watch(() => [props.targetChunkId, props.chunks] as const, ([id, chunks]) => {
  const page = chunks.find(c => c.id === id)?.startPageId
  if (page) targetPageId.value = page
}, { immediate: true })

// The highlight's part in each loaded chunk; it ends at a gap in chunk order.
const marked = computed(() => {
  const parts = new Map<string, { start: number, end: number }>()
  const h = props.highlight
  const anchor = h ? props.chunks.findIndex(c => c.id === h.chunkId) : -1
  if (!h || anchor < 0) return parts
  const ordered = props.chunks.map(c => ({ order: c.order ?? Number.NaN, text: c.text }))
  for (const part of projectSpan(ordered, anchor, h.start, h.end)) {
    parts.set(props.chunks[part.chunk].id, { start: part.start, end: part.end })
  }
  return parts
})

function textParts (chunk: DocumentChunk): { text: string, marked: boolean }[] {
  const part = marked.value.get(chunk.id)
  if (!part) return [{ text: chunk.text, marked: false }]
  return [
    { text: chunk.text.slice(0, part.start), marked: false },
    { text: chunk.text.slice(part.start, part.end), marked: true },
    { text: chunk.text.slice(part.end), marked: false }
  ].filter(p => p.text)
}

const documentTitle = computed(() => {
  const d = props.document
  if (!d) return ''
  const part = [d.partNumber, d.partName].filter(v => v !== null && v !== undefined && v !== '').join(' ')
  return [d.title || 'Untitled document', d.subtitle, part].filter(Boolean).join(' – ')
})

const headerEl = ref<HTMLElement | null>(null)

// With `scrollText`: whether the target is scrolled out of the passage's view, and on which
// side, for the way back to it (`backLabel`). Checked on scrolling and on layout changes.
const bodyEl = ref<HTMLElement | null>(null)
const targetAway = ref<'above' | 'below' | null>(null)
let checkFrame = 0
function checkTargetInView () {
  if (checkFrame) return
  checkFrame = requestAnimationFrame(() => {
    checkFrame = 0
    const body = bodyEl.value
    if (!props.scrollText || !props.backLabel || !body || !props.targetChunkId || !props.chunks.length) {
      targetAway.value = null
      return
    }
    const target = body.querySelector<HTMLElement>('[data-testid="chunk-context-mark"]') ??
      (props.targetChunkId ? chunkEls.get(props.targetChunkId) : undefined)
    // Extending the passage dropped the target: the way back reloads it.
    if (!target) { targetAway.value = 'below'; return }
    const view = body.getBoundingClientRect()
    const rect = target.getBoundingClientRect()
    targetAway.value = rect.bottom < view.top + 4 ? 'above' : rect.top > view.bottom - 4 ? 'below' : null
  })
}

// With `scrollText`: whether there is text beyond the top / bottom edge of the passage's view.
const fadeTop = ref(false)
const fadeBottom = ref(false)
function updateFades () {
  const body = bodyEl.value
  if (!props.scrollText || !body) {
    fadeTop.value = false
    fadeBottom.value = false
    return
  }
  fadeTop.value = body.scrollTop > 1
  fadeBottom.value = body.scrollHeight - body.clientHeight - body.scrollTop > 1
}
function onBodyScroll () {
  updateFades()
  checkTargetInView()
}
const bodyObserver = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => { updateFades(); checkTargetInView() })
watch(bodyEl, (el, old) => {
  if (old) bodyObserver?.unobserve(old)
  if (el) bodyObserver?.observe(el)
  updateFades()
})
watch(() => [props.chunks, props.highlight, props.targetChunkId, props.scrollText, props.loading] as const, () => {
  void nextTick(() => { updateFades(); checkTargetInView() })
})
onBeforeUnmount(() => {
  bodyObserver?.disconnect()
  if (checkFrame) cancelAnimationFrame(checkFrame)
})

/** The point of a DOM selection boundary in a chunk's text, or null outside the text. */
function textPoint (node: Node, offset: number): ContextTextPoint | null {
  const element = node instanceof Element ? node : node.parentElement
  const text = element?.closest('[data-chunk-text]')
  const chunkId = text?.closest<HTMLElement>('[data-chunk-id]')?.dataset.chunkId
  if (!text || !chunkId) return null
  const before = window.document.createRange()
  before.setStart(text, 0)
  before.setEnd(node, offset)
  return { chunkId, offset: before.toString().length }
}

/** The text selected in the shown passage, as its two ends, or null (nothing selected there). */
function textSelection (): [ContextTextPoint, ContextTextPoint] | null {
  const selected = window.getSelection()
  if (!selected || selected.rangeCount === 0 || selected.isCollapsed) return null
  const range = selected.getRangeAt(0)
  const from = textPoint(range.startContainer, range.startOffset)
  const to = textPoint(range.endContainer, range.endOffset)
  return from && to ? [from, to] : null
}

defineExpose({ textSelection })

// Chunk elements by id, to bring the target into view.
const chunkEls = new Map<string, HTMLElement>()
function setChunkEl (id: string, el: HTMLElement | null) {
  if (el) chunkEls.set(id, el)
  else chunkEls.delete(id)
}

// Set by every request to show the target; cleared once it is in view.
let scrollPending = true
watch(() => props.focusRequest, () => { scrollPending = true })

// The target last scrolled to: the next one in the same document is scrolled to from its
// side, so the motion shows whether it is earlier or later in the text (#493).
let lastScrolled: { documentId: string, chunkId: string, order: number } | null = null

function directionTo (documentId: string | undefined, order: number | null | undefined): -1 | 0 | 1 {
  if (!lastScrolled || !documentId || order == null || lastScrolled.documentId !== documentId) return 0
  return Math.sign(order - lastScrolled.order) as -1 | 0 | 1
}

watch(() => [props.focusRequest, props.loading, targetLoaded.value, props.visible] as const, async ([request, loading, loaded, visible], previous) => {
  // A new request is noted here too: watchers of one change do not run in a fixed order, and
  // with the target already loaded nothing else would run this again.
  if (previous && request !== previous[0]) scrollPending = true
  if (loading || !loaded || !visible || !scrollPending) return
  await nextTick()
  // A panel just made visible is laid out in the next frame.
  await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
  if (!props.visible || !scrollPending) return
  const el = props.targetChunkId ? chunkEls.get(props.targetChunkId) : undefined
  if (!el) return
  scrollPending = false
  const documentId = props.document?.id
  const order = props.chunks.find(c => c.id === props.targetChunkId)?.order
  const direction = directionTo(documentId, order)
  // The previous target's chunk is gone: the passage was replaced, its old position means nothing.
  const replaced = !!lastScrolled && !props.chunks.some(c => c.id === lastScrolled?.chunkId)
  lastScrolled = documentId && order != null && props.targetChunkId
    ? { documentId, chunkId: props.targetChunkId, order }
    : null
  // A marked range (an annotation) is what is shown, not its chunk: in a long chunk the
  // chunk's start can be a screen away from it. Clear of the sticky header; a target
  // taller than half the screen shows from its start.
  const target = el.querySelector<HTMLElement>('[data-testid="chunk-context-mark"]') ?? el
  const inset = (props.scrollText ? 0 : headerEl.value?.offsetHeight ?? 0) + 8
  target.style.scrollMarginTop = `${inset}px`
  const tall = target.getBoundingClientRect().height > window.innerHeight / 2
  scrollToTarget(target, direction, tall, inset, replaced)
}, { immediate: true })
</script>

<style scoped>
.chunk-context__header {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 8px 0 4px;
  background: #fff;
  border-bottom: 1px solid rgba(0, 0, 0, 0.12);
}

.chunk-context__body {
  display: contents;
}

.chunk-context--scroll-text {
  flex-wrap: nowrap;
}

.chunk-context--scroll-text > .chunk-context__header {
  position: static;
  flex: none;
}

/* Fills the rest of the panel; a header too tall for a short screen leaves it a minimum,
   and the sidebar then scrolls the whole panel. */
.chunk-context--scroll-text > .chunk-context__body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1 1 0;
  min-height: 160px;
  overflow-y: auto;
  overflow-anchor: auto;
}

/* Zero-height anchors at the passage's edges carry the fades (they take no room and
   let every click, selection and touch through). */
.chunk-context__fade-anchor {
  position: sticky;
  z-index: 1;
  height: 0;
  margin: -4px 0;
  pointer-events: none;
}

.chunk-context__fade-anchor--top {
  top: 0;
}

.chunk-context__fade-anchor--bottom {
  bottom: 0;
}

.chunk-context__fade {
  position: absolute;
  left: 0;
  right: 0;
  height: 14px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s;
}

.chunk-context__fade--on {
  opacity: 1;
}

.chunk-context__fade-anchor--top .chunk-context__fade {
  top: 0;
  background: linear-gradient(to bottom, #fff, rgba(255, 255, 255, 0));
}

.chunk-context__fade-anchor--bottom .chunk-context__fade {
  bottom: 0;
  background: linear-gradient(to top, #fff, rgba(255, 255, 255, 0));
}

@media (prefers-reduced-motion: reduce) {
  .chunk-context__fade {
    transition: none;
  }
}

.chunk-context__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0 12px;
}

.chunk-context__title--link {
  color: inherit;
  text-decoration: none;
}

.chunk-context__title--link:hover,
.chunk-context__title--link:focus-visible {
  color: var(--q-primary);
  text-decoration: underline;
}

.chunk-context__title-icon {
  margin-left: 4px;
  vertical-align: -1px;
  color: var(--q-primary);
}

/* Zero-height anchors at the passage's edges keep the way back to the target in view. */
.chunk-context__back-anchor {
  position: sticky;
  z-index: 2;
  height: 0;
  margin: -4px 0;
  display: flex;
  justify-content: center;
}

.chunk-context__back-anchor--top {
  top: 0;
}

.chunk-context__back-anchor--bottom {
  bottom: 0;
}

.chunk-context__back {
  position: absolute;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.25);
}

.chunk-context__back-anchor--top .chunk-context__back {
  top: 8px;
}

.chunk-context__back-anchor--bottom .chunk-context__back {
  bottom: 8px;
}

.chunk-context__heading {
  margin-top: 8px;
  line-height: 1.4;
  color: rgba(0, 0, 0, 0.6);
}

.chunk-context__reloading {
  position: absolute;
  bottom: 6px;
  right: 0;
}

.chunk-context__open,
.chunk-context__return {
  margin-left: -6px;
}

.chunk-context__title {
  line-height: 1.3;
  overflow-wrap: anywhere;
}

/* Above a passage that scrolls by itself, a long title takes two lines (the whole one in its
   tooltip), so the fixed header leaves the passage room on a phone. */
.chunk-context--scroll-text .chunk-context__title {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
}

.chunk-context__text {
  /* Lets the browser keep the reading position when earlier text is added above. */
  overflow-anchor: auto;
}

.chunk-context__chunk {
  padding: 6px 8px;
  border-left: 3px solid transparent;
  border-radius: 2px;
}

.chunk-context__chunk + .chunk-context__chunk {
  margin-top: 4px;
}

.chunk-context__chunk--target {
  border-left-color: var(--q-primary);
  background-color: #fff8d6;
}

.chunk-context__mark {
  background-color: #ffd54f;
  color: inherit;
  border-radius: 2px;
  box-shadow: 0 0 0 1px #c49000;
}

.chunk-context__mark--pending {
  background-color: #b3e5fc;
  box-shadow: 0 0 0 1px #0277bd;
  outline: 1px dashed #01579b;
  outline-offset: 1px;
}

.chunk-context__target-label {
  color: var(--q-primary);
  line-height: 1.2;
}

.chunk-context__chunk-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: #333;
}

.chunk-context__edge {
  text-align: center;
  font-style: italic;
}
</style>
