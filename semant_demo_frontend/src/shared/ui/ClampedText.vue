<template>
  <!-- Text cut after `lines` lines, with "Show more" when it is longer; line breaks are kept. -->
  <div class="clamped-text">
    <div
      ref="body"
      class="clamped-text__body"
      :class="{ collapsed: !expanded }"
      :style="{ '-webkit-line-clamp': props.lines }"
    >
      {{ props.text }}
    </div>
    <button
      v-if="overflows || expanded"
      type="button"
      class="clamped-text__toggle text-primary"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      {{ expanded ? 'Show less' : 'Show more' }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  text: string
  lines?: number
}>(), { lines: 3 })

const expanded = ref(false)
const body = ref<HTMLElement | null>(null)
const overflows = ref(false)

function measure () {
  const el = body.value
  if (el && !expanded.value) overflows.value = el.scrollHeight > el.clientHeight + 1
}

let observer: ResizeObserver | null = null
onMounted(() => {
  measure()
  if (typeof ResizeObserver !== 'undefined' && body.value) {
    observer = new ResizeObserver(measure)
    observer.observe(body.value)
  }
})
watch(() => [props.text, props.lines], () => nextTick(measure))
onBeforeUnmount(() => observer?.disconnect())
</script>

<style scoped>
.clamped-text__body {
  white-space: pre-line;
  overflow-wrap: anywhere;
}

.clamped-text__body.collapsed {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Even expanded, a long text scrolls instead of growing without bound. */
.clamped-text__body:not(.collapsed) {
  max-height: 18em;
  overflow-y: auto;
}

.clamped-text__toggle {
  padding: 0;
  border: none;
  background: none;
  font-size: 12px;
  cursor: pointer;
}

.clamped-text__toggle:hover,
.clamped-text__toggle:focus-visible {
  text-decoration: underline;
}
</style>
