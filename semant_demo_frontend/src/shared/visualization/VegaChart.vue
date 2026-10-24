<template>
  <div class="vega-chart">
    <div ref="container" class="vega-chart__canvas" role="img" :aria-label="label" />
    <div v-if="failed" class="vega-chart__error text-caption text-negative">
      The chart could not be drawn.
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Draws one Vega-Lite (or Vega) specification with vega-embed, which is loaded only when a
 * chart is shown. The component owns embedding, resizing and disposal; the page owns the
 * data, its loading and errors, and supplies an accessible alternative (a table) itself:
 * the drawing is one image labelled `label`.
 *
 * A Vega-Lite specification gets the width of its container (`width`/`autosize` are set
 * here) and is drawn again when that width changes. A Vega specification is drawn as given.
 *
 * Drawings can overlap (a resize during a spec change) and finish in any order, so each one
 * is made in its own detached element. Only the newest is put into the container; an older
 * one finishing late is finalized without ever being shown.
 *
 * The Vega signals named in `signals` (e.g. an interval selection) are reported as
 * `signal` events of the shown drawing, so the page can react to an interaction without
 * the chart being drawn again on every pointer movement.
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Result, VisualizationSpec } from 'vega-embed'
import { loadEmbed } from './loadEmbed'

const props = defineProps<{
  spec: VisualizationSpec
  /** Accessible name of the drawing. */
  label: string
  /** Names of Vega signals to report as `signal` events. */
  signals?: string[]
}>()

const emit = defineEmits<{ signal: [name: string, value: unknown] }>()

const container = ref<HTMLElement | null>(null)
const failed = ref(false)

const FALLBACK_WIDTH = 400

let result: Result | null = null
let generation = 0
let width = 0
let observer: ResizeObserver | null = null

function isVegaLite (spec: VisualizationSpec): boolean {
  const schema = (spec as { $schema?: unknown }).$schema
  return typeof schema !== 'string' || schema.includes('vega-lite')
}

function sized (spec: VisualizationSpec): VisualizationSpec {
  if (!isVegaLite(spec)) return spec
  return { ...spec, width: width || FALLBACK_WIDTH, autosize: { type: 'fit-x', contains: 'padding' } }
}

function dispose () {
  result?.finalize()
  result = null
  container.value?.replaceChildren()
}

async function render () {
  const current = ++generation
  if (!container.value) return
  const drawing = document.createElement('div')
  drawing.className = 'vega-chart__drawing'
  try {
    const embed = await loadEmbed()
    if (current !== generation) return
    const embedded = await embed(drawing, sized(props.spec), { actions: false, renderer: 'svg' })
    if (current !== generation || !container.value) {
      embedded.finalize()
      return
    }
    dispose()
    container.value.appendChild(drawing)
    result = embedded
    for (const name of props.signals ?? []) {
      embedded.view.addSignalListener(name, (signal, value) => emit('signal', signal, value))
    }
    failed.value = false
  } catch (e) {
    if (current !== generation) return
    console.error('Drawing a chart failed', e)
    dispose()
    failed.value = true
  }
}

function measure (): number {
  return Math.floor(container.value?.clientWidth ?? 0)
}

onMounted(() => {
  width = measure()
  void render()
  if (typeof ResizeObserver === 'undefined' || !container.value) return
  observer = new ResizeObserver(() => {
    const next = measure()
    if (next && Math.abs(next - width) >= 1) {
      width = next
      void render()
    }
  })
  observer.observe(container.value)
})

watch(() => props.spec, () => { void render() })

onBeforeUnmount(() => {
  generation++
  observer?.disconnect()
  observer = null
  dispose()
})
</script>

<style scoped>
.vega-chart {
  width: 100%;
  min-width: 0;
}

.vega-chart__canvas {
  width: 100%;
}
</style>
