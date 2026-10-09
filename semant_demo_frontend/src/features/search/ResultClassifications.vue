<template>
  <div v-if="badges.length" class="result-classifications row no-wrap items-start q-mt-xs">
    <div ref="line" class="classification-line col" :class="{ collapsed: !expanded }">
      <q-badge
        v-for="badge in badges"
        :key="badge.key"
        :color="badge.color.bg"
        :text-color="badge.color.text"
        class="classification-badge"
      >
        <span class="visually-hidden">{{ badge.category }}: </span>{{ badge.value }}
        <q-tooltip>{{ badge.category }}: {{ badge.value }}</q-tooltip>
      </q-badge>
    </div>
    <button
      v-if="hiddenCount > 0"
      type="button"
      class="classification-toggle text-primary q-ml-sm"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      {{ expanded ? 'Show less' : `+${hiddenCount} more` }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { SearchFilter } from 'src/generated/api'
import { classificationBadges } from './classifications'

const props = withDefaults(defineProps<{
  metadata?: Record<string, string[]> | null
  filters: readonly SearchFilter[]
}>(), { metadata: null })

// Local to this result; never part of the search or filter state.
const expanded = ref(false)
const badges = computed(() => classificationBadges(props.metadata, props.filters))

// Badges wrapping below the first line; they are clipped until expanded.
const line = ref<HTMLElement | null>(null)
const hiddenCount = ref(0)

function measure () {
  const items = Array.from(line.value?.children ?? []) as HTMLElement[]
  const firstTop = items[0]?.offsetTop ?? 0
  hiddenCount.value = items.filter(item => item.offsetTop > firstTop).length
}

let observer: ResizeObserver | null = null
onMounted(() => {
  measure()
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(measure)
    watch(line, (el, old) => {
      if (old) observer?.unobserve(old)
      if (el) observer?.observe(el)
    }, { immediate: true })
  }
})
watch(badges, () => nextTick(measure))
onBeforeUnmount(() => observer?.disconnect())
</script>

<style scoped>
.classification-line {
  position: relative; /* badge offsetTop is measured from the line */
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-width: 0;
}

.classification-line.collapsed {
  max-height: 20px; /* one row of badges */
  overflow: hidden;
}

.classification-badge {
  height: 20px;
  line-height: 16px;
  padding: 2px 6px;
  max-width: 100%;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.classification-toggle {
  flex: none;
  height: 20px;
  padding: 0;
  border: none;
  background: none;
  font-size: 12px;
  line-height: 20px;
  white-space: nowrap;
  cursor: pointer;
}

.classification-toggle:hover,
.classification-toggle:focus-visible {
  text-decoration: underline;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
