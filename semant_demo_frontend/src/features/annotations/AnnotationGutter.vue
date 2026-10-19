<template>
  <div class="span-gutter-wrapper">
    <div class="span-gutter" :style="{ width: gutterWidth + 'px', height: gutterHeight + 'px' }">
      <div
        v-for="item in markers"
        :key="item.spanId"
        class="gutter-item"
        :class="{ 'is-active': hoveredSpanId === item.spanId, 'is-auto': item.isAuto, 'is-highlighted': highlightedSpanId === item.spanId }"
        :style="{
          top: item.top + 'px',
          height: item.height + 'px',
          right: item.column * COLUMN_WIDTH + GUTTER_PADDING + 'px',
          '--tag-color': tagInfo(item.tagId).color
        }"
        :title="tagInfo(item.tagId).name + (item.isAuto ? ' (AI suggestion)' : '')"
        @mouseenter="emit('hover', item.spanId)"
        @mouseleave="emit('hover', null)"
        @click.stop="emit('select', item, $event)"
      >
        <div class="gutter-label">
          <q-icon :name="item.isAuto ? 'auto_awesome' : tagInfo(item.tagId).pictogram" size="10px" class="gutter-icon" />
          <span class="gutter-shorthand">{{ tagInfo(item.tagId).shorthand }}</span>
        </div>
        <div class="gutter-line"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Tag } from 'src/generated/api'
import type { SpanMarker } from './AnnotationGutterTypes'

// Span markers left of the document text, one column per span sharing lines with another,
// column 0 next to the text. Each marker is a fixed-width label on the span's first line
// and a line down to its last one; AI suggestions are dashed. More columns than fit make
// the gutter scroll sideways, starting at the text side.
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

const COLUMN_WIDTH = 56
const GUTTER_PADDING = 4
const UNKNOWN_TAG = { name: 'Unknown tag', color: '#3b82f6', shorthand: '?', pictogram: 'label' }

const tagInfoMap = computed(() => {
  const map: Record<string, { name: string; color: string; shorthand: string; pictogram: string }> = {}
  for (const tag of props.tags) {
    map[tag.id] = { name: tag.name, color: tag.color, shorthand: tag.shorthand || tag.name.slice(0, 3), pictogram: tag.pictogram || 'label' }
  }
  return map
})

const tagInfo = (tagId: string) => tagInfoMap.value[tagId] ?? UNKNOWN_TAG

const gutterWidth = computed(() => {
  if (!props.markers.length) return 0
  const maxCol = Math.max(...props.markers.map(i => i.column))
  return (maxCol + 1) * COLUMN_WIDTH + 2 * GUTTER_PADDING
})

const gutterHeight = computed(() => {
  if (!props.markers.length) return 0
  return Math.max(...props.markers.map(i => i.top + i.height))
})
</script>

<style scoped>
/* Four columns wide. `direction: rtl` starts the sideways scroll at the text side; the
   gutter never handles vertical wheel events, so they scroll the document. */
.span-gutter-wrapper {
  flex: none;
  width: 232px;
  position: relative;
  overflow-x: auto;
  overflow-y: hidden;
  direction: rtl;
  background: #f4f6fa;
  border-right: 1px solid #dde3ec;
}

/* Two columns on a phone. */
@media (max-width: 599px) {
  .span-gutter-wrapper {
    width: 120px;
  }
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
  direction: ltr;
  position: relative;
  min-width: 100%;
}

.gutter-item {
  position: absolute;
  width: 52px;
  cursor: pointer;
}

/* The line next to the text, from the span's first line to its last. */
.gutter-line {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  border-radius: 2px;
  background-color: var(--tag-color);
  opacity: 0.75;
  transition: opacity 0.15s, width 0.15s;
}

.gutter-item:hover .gutter-line,
.gutter-item.is-active .gutter-line,
.gutter-item.is-highlighted .gutter-line {
  opacity: 1;
  width: 4px;
}

/* Fixed width; a long shorthand is cut off. */
.gutter-label {
  position: absolute;
  left: 0;
  top: 0;
  width: 44px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 0.65rem;
  font-weight: 700;
  padding: 2px 4px;
  border: 1.5px solid var(--tag-color);
  border-radius: 4px;
  background-color: var(--tag-color);
  color: #fff;
  white-space: nowrap;
  line-height: 1.4;
  opacity: 0.85;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.18);
  transition: opacity 0.15s, box-shadow 0.15s;
}

.gutter-icon {
  flex: none;
  opacity: 0.9;
}

.gutter-shorthand {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.gutter-item:hover .gutter-label,
.gutter-item.is-active .gutter-label {
  opacity: 1;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
}

/* ── AI suggestions: the tag colour, dashed. ── */
.gutter-item.is-auto .gutter-line {
  background-color: transparent;
  background-image: repeating-linear-gradient(
    to bottom,
    var(--tag-color) 0,
    var(--tag-color) 5px,
    transparent 5px,
    transparent 9px
  );
}

.gutter-item.is-auto .gutter-label {
  background-color: #fff;
  color: var(--tag-color);
  border-style: dashed;
}

/* Two-way highlight with the AI suggestions panel: when a card is selected in the panel,
   ring its marker. The same class is added when the user clicks an auto span in the
   text or gutter so the panel mirrors the choice. */
.gutter-item.is-highlighted .gutter-label {
  opacity: 1;
  box-shadow: 0 0 0 2px #f4f6fa, 0 0 0 4px var(--tag-color);
}
</style>
