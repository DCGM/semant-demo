<template>
  <div class="rail-container">
    <div ref="railRef" class="rail-overlay">
      <div
        v-for="marker in renderedMarkers"
        :key="marker.markerId"
        class="rail-item"
        :style="{ top: `${marker.top}px`, minHeight: `${marker.height}px` }"
      >
        <span
          class="rail-color"
          :style="{ backgroundColor: marker.tagColor, height: `${marker.height}px` }"
        />
        <span class="rail-label">{{ marker.tagName }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { AvailableTag } from './ChunkTagAnnotator.vue'

interface AnnotationMarker {
  markerId: string
  chunkId: string
  start: number
  tagId: string
}

interface Props {
  markers: AnnotationMarker[]
  availableTags: AvailableTag[]
}

const props = defineProps<Props>()

const railRef = ref<HTMLElement | null>(null)
const markerPositions = ref<Record<string, { top: number; height: number }>>({})
let rafId: number | null = null

const tagsById = computed(() => {
  return props.availableTags.reduce<Record<string, AvailableTag>>((acc, tag) => {
    if (tag.tagUuid) {
      acc[tag.tagUuid] = tag
    }
    return acc
  }, {})
})

const renderedMarkers = computed(() => {
  return props.markers
    .map((marker) => {
      const tag = tagsById.value[marker.tagId]
      const position = markerPositions.value[marker.markerId]
      if (!tag || position === undefined) return null

      return {
        markerId: marker.markerId,
        top: position.top,
        height: position.height,
        tagName: tag.tagName,
        tagColor: tag.tagColor
      }
    })
    .filter((marker): marker is NonNullable<typeof marker> => marker !== null)
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

  for (const marker of props.markers) {
    const selector = `.text-segment[data-chunk-id="${marker.chunkId}"][data-start="${marker.start}"]`
    const segment = document.querySelector(selector) as HTMLElement | null
    if (!segment) continue

    const segmentRect = segment.getBoundingClientRect()
    nextPositions[marker.markerId] = {
      top: segmentRect.top - railRect.top,
      height: segmentRect.height
    }
  }

  markerPositions.value = nextPositions
}

watch(
  () => [props.markers, props.availableTags],
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
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}

.rail-color {
  width: 8px;
  min-width: 8px;
  border-radius: 8px;
}

.rail-label {
  font-size: 1rem;
  color: #303030;
}
</style>
