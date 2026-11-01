<template>
  <!-- Badges that wrap, clipped after `lines` lines with a "+N more" toggle that expands them in
       place (first used by the Search result classifications, #177). With `expandedLines`, the
       expanded badges scroll within that many lines, so a long list never grows without bound. -->
  <div class="wrapping-badges row no-wrap items-start">
    <div
      ref="line"
      class="wrapping-badges__line col"
      :class="{ collapsed: !expanded, scrolls: expanded && !!props.expandedLines }"
      :style="{ maxHeight: maxHeight }"
    >
      <slot />
    </div>
    <button
      v-if="hiddenCount > 0"
      type="button"
      class="wrapping-badges__toggle text-primary q-ml-sm"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      {{ expanded ? 'Show less' : `+${hiddenCount} more` }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  /** Changes when the badges change, so they are measured again. */
  watchKey?: unknown
  /** Lines shown before "+N more". */
  lines?: number
  /** Lines the expanded badges take at most before they scroll; none: all of them. */
  expandedLines?: number
  /** The height of one badge, in px. */
  badgeHeight?: number
}>(), { lines: 1, badgeHeight: 20 })

const GAP = 4

// Local to this list; never part of a filter or of the page state.
const expanded = ref(false)

const linesHeight = (lines: number) => `${lines * props.badgeHeight + (lines - 1) * GAP}px`
const maxHeight = computed(() => {
  if (!expanded.value) return linesHeight(props.lines)
  return props.expandedLines ? linesHeight(props.expandedLines) : undefined
})

// Badges wrapping below the shown lines; they are clipped until expanded.
const line = ref<HTMLElement | null>(null)
const hiddenCount = ref(0)

function measure () {
  const items = Array.from(line.value?.children ?? []) as HTMLElement[]
  const tops = [...new Set(items.map(item => item.offsetTop))].sort((a, b) => a - b)
  const lastShown = tops[props.lines - 1] ?? Infinity
  hiddenCount.value = items.filter(item => item.offsetTop > lastShown).length
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
watch(() => [props.watchKey, props.lines], () => nextTick(measure), { deep: true })
onBeforeUnmount(() => observer?.disconnect())
</script>

<style scoped>
.wrapping-badges__line {
  position: relative; /* badge offsetTop is measured from the line */
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-width: 0;
}

.wrapping-badges__line.collapsed {
  overflow: hidden;
}

.wrapping-badges__line.scrolls {
  overflow-y: auto;
}

.wrapping-badges__toggle {
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

.wrapping-badges__toggle:hover,
.wrapping-badges__toggle:focus-visible {
  text-decoration: underline;
}
</style>
