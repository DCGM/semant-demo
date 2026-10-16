<template>
  <div class="span-gutter-wrapper" @wheel.prevent="onWheel">
    <div class="span-gutter" :style="{ width: gutterWidth + 'px', height: gutterHeight + 'px' }">
      <div
        v-for="item in markers"
        :key="item.spanId"
        class="gutter-item"
        :class="{ 'is-active': hoveredSpanId === item.spanId, 'is-auto': item.isAuto, 'is-highlighted': highlightedSpanId === item.spanId }"
        :style="{
          top: item.top + 'px',
          height: item.height + 'px',
          left: item.column * COLUMN_WIDTH + 8 + 'px',
          '--tag-color': tagInfo(item.tagId).color
        }"
        @mouseenter="emit('hover', item.spanId)"
        @mouseleave="emit('hover', null)"
        @click.stop="emit('select', item, $event)"
      >
        <div class="gutter-line" :style="{ backgroundColor: tagInfo(item.tagId).color }"></div>
        <div class="gutter-label" :style="{ backgroundColor: tagInfo(item.tagId).color }">
          <q-icon :name="tagInfo(item.tagId).pictogram" size="10px" class="gutter-icon" />
          {{ tagInfo(item.tagId).shorthand }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Tag } from 'src/generated/api'
import type { SpanMarker } from './AnnotationGutterTypes'

// Span markers beside the document text, one column per overlapping span. Auto
// (AI-suggested) spans have muted, dashed markers.
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

const COLUMN_WIDTH = 44
const UNKNOWN_TAG = { color: '#3b82f6', shorthand: '?', pictogram: 'label' }

const tagInfoMap = computed(() => {
  const map: Record<string, { color: string; shorthand: string; pictogram: string }> = {}
  for (const tag of props.tags) {
    map[tag.id] = { color: tag.color, shorthand: tag.shorthand || tag.name.slice(0, 3), pictogram: tag.pictogram || 'label' }
  }
  return map
})

const tagInfo = (tagId: string) => tagInfoMap.value[tagId] ?? UNKNOWN_TAG

const gutterWidth = computed(() => {
  if (!props.markers.length) return 0
  const maxCol = Math.max(...props.markers.map(i => i.column))
  return (maxCol + 1) * COLUMN_WIDTH
})

const gutterHeight = computed(() => {
  if (!props.markers.length) return 0
  return Math.max(...props.markers.map(i => i.top + i.height))
})

const onWheel = (e: WheelEvent) => {
  const wrapper = (e.currentTarget as HTMLElement)
  wrapper.scrollLeft += e.deltaY
}
</script>

<style scoped>
.span-gutter-wrapper {
  flex: 1;
  min-width: 60px;
  position: relative;
  overflow-x: auto;
  overflow-y: hidden;
  background: #ffffff;
  border-radius: 0 16px 16px 0;
  box-shadow: none;
}

.span-gutter-wrapper::-webkit-scrollbar {
  height: 6px;
}

.span-gutter-wrapper::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.04);
  border-radius: 3px;
  margin: 0 4px;
}

.span-gutter-wrapper::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.18);
  border-radius: 3px;
}

.span-gutter-wrapper::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.3);
}

.span-gutter {
  position: relative;
  min-width: 100%;
  padding: 0 4px;
}

.gutter-item {
  position: absolute;
  width: 40px;
  cursor: pointer;
}

.gutter-line {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  border-radius: 2px;
  opacity: 0.7;
  transition: opacity 0.15s;
}

.gutter-item:hover .gutter-line,
.gutter-item.is-active .gutter-line {
  opacity: 1;
}

.gutter-label {
  position: absolute;
  left: 8px;
  top: 0;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 0.65rem;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  color: #fff;
  white-space: nowrap;
  line-height: 1.4;
  opacity: 0.8;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.18);
  transition: opacity 0.15s;
}

.gutter-icon {
  opacity: 0.9;
}

.gutter-item:hover .gutter-label,
.gutter-item.is-active .gutter-label {
  opacity: 1;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
}

/* ── Auto (AI-suggested) gutter items: muted, dashed, slightly faded. ── */
.gutter-item.is-auto .gutter-line {
  /* Replace solid colour with a dashed strip so users can spot at a glance
     that this is an unconfirmed AI suggestion. The inline `backgroundColor`
     (tag colour) is intentionally overridden — but we need to use
     `background-image` only (not the `background` shorthand) so the inline
     `background-color` isn't wiped, which would make the bar disappear
     whenever we re-enable it (e.g. on highlight). */
  background-image: repeating-linear-gradient(
    to bottom,
    currentColor 0,
    currentColor 4px,
    transparent 4px,
    transparent 8px
  ) !important;
  background-color: transparent !important;
  color: #94a3b8;
  opacity: 0.55;
  filter: grayscale(0.6);
}

.gutter-item.is-auto .gutter-label {
  background-color: #94a3b8 !important;
  opacity: 0.7;
  filter: grayscale(0.5);
}

.gutter-item.is-auto:hover .gutter-line,
.gutter-item.is-auto.is-active .gutter-line {
  opacity: 0.85;
}

.gutter-item.is-auto:hover .gutter-label,
.gutter-item.is-auto.is-active .gutter-label {
  opacity: 0.95;
}

/* Two-way highlight with the AI suggestions panel: when a card is selected
   in the panel, emphasize the gray dashed marker (darker color, full
   opacity) without restoring the tag's full colour. The same class is
   added when the user clicks an auto span in the text/gutter so the panel
   mirrors the choice. */
.gutter-item.is-auto.is-highlighted .gutter-line {
  color: #475569;
  opacity: 1;
  filter: none;
}

.gutter-item.is-auto.is-highlighted .gutter-label {
  background-color: #475569 !important;
  opacity: 1;
  filter: none;
}
</style>
