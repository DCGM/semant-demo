<template>
  <div class="rail-container">
    <div ref="railRef" class="rail-overlay">
      <div
        v-for="marker in renderedMarkers"
        :key="marker.markerId"
        class="rail-item"
        :style="{
          top: `${marker.top}px`,
          left: `${marker.left}px`,
          minHeight: `${marker.height}px`,
          opacity: `${marker.opacity}`,
          zIndex: `${marker.zIndex}`
        }"
        role="button"
        tabindex="0"
        @click="emit('markerClick', marker.rawMarker)"
        @mouseenter="emit('markerHoverStart', marker.rawMarker)"
        @mouseleave="emit('markerHoverEnd')"
        @keydown.enter.prevent="emit('markerClick', marker.rawMarker)"
        @keydown.space.prevent="emit('markerClick', marker.rawMarker)"
      >
        <span
          class="rail-color"
          :style="{
            backgroundColor: marker.tagColor,
            height: `${marker.height}px`,
            zIndex: marker.zIndex
          }"
        />
        <span
          class="rail-label"
          :style="{
            zIndex: marker.zIndex + 1,
            borderColor: marker.tagColor
          }"
        >
          <q-icon
            :name="marker.tagPictogram"
            :style="{ color: marker.tagColor }"
            class="rail-label-icon"
          />
          {{ marker.tagShorthand }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { AvailableTag } from './ChunkTagAnnotator.vue'
import type { SpanType } from 'src/generated/api/models/SpanType'

interface AnnotationMarker {
  markerId: string
  spanId: string | null
  chunkId: string
  start: number
  end: number
  spanType?: SpanType | null
  tagId: string
}

interface Props {
  markers: AnnotationMarker[]
  availableTags: AvailableTag[]
  layoutTrigger?: string | number
  hoveredMarker?: {
    spanId: string | null
    tagId: string
    spanType?: SpanType | null
  } | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  markerClick: [marker: AnnotationMarker]
  markerHoverStart: [marker: AnnotationMarker]
  markerHoverEnd: []
}>()

const railRef = ref<HTMLElement | null>(null)
const markerPositions = ref<Record<string, { top: number; height: number }>>({})
let rafId: number | null = null

const tagsById = computed(() => {
  return props.availableTags.reduce<Record<string, AvailableTag>>(
    (acc, tag) => {
      if (tag.tagUuid) {
        acc[tag.tagUuid] = tag
      }
      return acc
    },
    {}
  )
})

const renderedMarkers = computed(() => {
  const hoveredSpanId = props.hoveredMarker?.spanId || null
  const shouldDimOthers = hoveredSpanId !== null

  const baseMarkers = props.markers
    .map((marker) => {
      const tag = tagsById.value[marker.tagId]
      const position = markerPositions.value[marker.markerId]
      if (!tag || position === undefined) return null

      const isActive = !!hoveredSpanId && marker.spanId === hoveredSpanId

      return {
        rawMarker: marker,
        markerId: marker.markerId,
        top: position.top,
        height: position.height,
        tagName: tag.tagName,
        tagColor: tag.tagColor,
        tagPictogram: tag.tagPictogram,
        tagShorthand: tag.tagShorthand,
        opacity: shouldDimOthers && !isActive ? 0.35 : 1
      }
    })
    .filter((marker): marker is NonNullable<typeof marker> => marker !== null)

  // Assign horizontal lanes so vertically overlapping markers do not collide.
  const sortedMarkers = [...baseMarkers].sort((a, b) => a.top - b.top)
  const laneEndByIndex: number[] = []
  const overlapPadding = 1
  const laneOffsetPx = 22

  return sortedMarkers.map((marker) => {
    let lane = laneEndByIndex.findIndex(
      (laneEnd) => marker.top >= laneEnd + overlapPadding
    )
    if (lane === -1) {
      lane = laneEndByIndex.length
      laneEndByIndex.push(0)
    }

    laneEndByIndex[lane] = marker.top + marker.height

    return {
      ...marker,
      left: lane * laneOffsetPx,
      zIndex: 100 + lane
    }
  })
})

const schedulePositionSync = () => {
  if (rafId !== null) return
  rafId = window.requestAnimationFrame(() => {
    rafId = null
    syncMarkerPositions()
  })
}

const syncMarkerPositions = () => {
  const rail = railRef.value
  if (!rail) return

  const railRect = rail.getBoundingClientRect()
  const nextPositions: Record<string, { top: number; height: number }> = {}

  const getSegmentsForMarker = (marker: AnnotationMarker): HTMLElement[] => {
    if (marker.spanId) {
      const candidates = document.querySelectorAll(
        '.text-segment[data-span-ids]'
      )
      const matched = Array.from(candidates).filter((node) => {
        const spanIds =
          (node.getAttribute('data-span-ids') || '')
            .split(/\s+/)
            .filter(Boolean) || []
        return spanIds.includes(marker.spanId as string)
      }) as HTMLElement[]

      if (matched.length > 0) {
        return matched
      }
    }

    const selector = `.text-segment[data-chunk-id="${marker.chunkId}"][data-start="${marker.start}"]`
    const segment = document.querySelector(selector) as HTMLElement | null
    return segment ? [segment] : []
  }

  for (const marker of props.markers) {
    const segments = getSegmentsForMarker(marker)
    if (!segments.length) continue

    const segmentRects = segments
      .map((segment) => segment.getBoundingClientRect())
      .filter((rect) => rect.height > 0)

    if (!segmentRects.length) continue

    const top = Math.min(...segmentRects.map((rect) => rect.top))
    const bottom = Math.max(...segmentRects.map((rect) => rect.bottom))

    nextPositions[marker.markerId] = {
      top: top - railRect.top,
      height: Math.max(2, bottom - top)
    }
  }

  markerPositions.value = nextPositions
}

watch(
  () => [props.markers, props.availableTags, props.layoutTrigger],
  async () => {
    await nextTick()
    schedulePositionSync()
  },
  { deep: true, immediate: true }
)

onMounted(() => {
  window.addEventListener('scroll', schedulePositionSync, { passive: true })
  window.addEventListener('resize', schedulePositionSync)
  schedulePositionSync()
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', schedulePositionSync)
  window.removeEventListener('resize', schedulePositionSync)
  if (rafId !== null) {
    window.cancelAnimationFrame(rafId)
    rafId = null
  }
})
</script>

<style scoped>
.rail-container {
  position: sticky;
  top: calc(64px + 12px);
  min-height: 280px;
  background: transparent;
}

.rail-overlay {
  position: relative;
  min-height: 260px;
}

.rail-item {
  position: absolute;
  width: max-content;
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.rail-color {
  position: relative;
  width: 6px;
  min-width: 6px;
  border-radius: 8px;
  z-index: 1;
}

.rail-color::before {
  content: '';
  position: absolute;
  top: -6px;
  right: -8px;
  bottom: -6px;
  left: -8px;
  z-index: 0;
}

.rail-label {
  font-size: 1rem;
  color: #303030;
  position: relative;
  z-index: 2;
  border: 1px solid transparent;
  padding: 2px 8px;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.rail-label-icon {
  font-size: 0.95rem;
}
</style>
