<template>
  <div v-if="chips.length" class="filter-chips" role="group" aria-label="Active filters" data-testid="concordance-chips">
    <span class="filter-chips__label">Filters:</span>
    <!-- At most two rows unless expanded; chips past them are hidden from sight and from the keyboard. -->
    <div ref="list" class="filter-chips__list">
      <q-chip
        v-for="chip in chips"
        :key="chip.key"
        removable
        dense
        :clickable="!!chip.opens"
        :icon="chip.opens ? 'join_inner' : undefined"
        :color="chip.opens ? 'amber-2' : 'blue-1'"
        text-color="dark"
        class="filter-chips__chip"
        :title="chip.opens ? 'Show this annotation' : undefined"
        :remove-aria-label="chip.opens ? `Stop finding annotations similar to ${chip.label}` : `Remove filter ${chip.group}: ${chip.label}`"
        :data-testid="`concordance-chip-${chip.key}`"
        @click="chip.opens && emit('open', chip.opens)"
        @remove="emit('change', chip.remove)"
      >
        <span class="filter-chips__group">{{ chip.group }}:</span>
        <span class="filter-chips__value" :title="chip.label">{{ chip.label }}</span>
      </q-chip>
    </div>
    <q-btn
      v-if="hidden > 0 || expanded"
      flat
      dense
      no-caps
      color="primary"
      :label="expanded ? 'Show fewer' : `+${hidden} more`"
      :aria-expanded="expanded ? 'true' : 'false'"
      :aria-label="expanded ? 'Show fewer active filters' : `Show ${hidden} more active filters`"
      data-testid="concordance-chips-more"
      @click="expanded = !expanded"
    />
    <q-btn
      flat
      dense
      no-caps
      color="primary"
      label="Reset filters"
      data-testid="concordance-chips-reset"
      @click="emit('reset')"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { QBtn, QChip } from 'quasar'
import type { AnnotatedDocument, AnnotationListRow, Attribute, Tag } from 'src/generated/api'
import type { ConcordanceFilters } from './concordanceStore'
import { concordanceChips } from './filterChips'

/** The concordance's active filters as removable chips, with a reset of all (#663); the source
 * of Find similar as a reference chip that opens it (#664). */
const props = defineProps<{
  filters: ConcordanceFilters
  tags: Tag[]
  documents: AnnotatedDocument[]
  attributes?: Attribute[]
}>()

const emit = defineEmits<{
  change: [change: Partial<ConcordanceFilters>]
  reset: []
  open: [row: AnnotationListRow]
}>()

const chips = computed(() => concordanceChips(props.filters, props.tags, props.documents, props.attributes ?? []))

const MAX_ROWS = 2
const list = ref<HTMLElement | null>(null)
const expanded = ref(false)
const hidden = ref(0)

/** Hides the chips that do not fit in the first two rows and shortens the list to those rows. */
function measure () {
  const el = list.value
  if (!el) return
  const items = Array.from(el.children) as HTMLElement[]
  el.style.maxHeight = ''
  for (const item of items) item.removeAttribute('data-clipped')
  if (expanded.value || !items.length) { hidden.value = 0; return }
  const tops = [...new Set(items.map(i => i.offsetTop))].sort((a, b) => a - b)
  if (tops.length <= MAX_ROWS) { hidden.value = 0; return }
  const limit = tops[MAX_ROWS]
  let count = 0
  let bottom = 0
  for (const item of items) {
    if (item.offsetTop >= limit) { item.setAttribute('data-clipped', ''); count++ } else bottom = Math.max(bottom, item.offsetTop + item.offsetHeight)
  }
  el.style.maxHeight = `${bottom}px`
  hidden.value = count
}

let observer: ResizeObserver | null = null
onMounted(() => {
  if (typeof ResizeObserver !== 'undefined' && list.value) {
    observer = new ResizeObserver(() => measure())
    observer.observe(list.value)
  }
  void nextTick(measure)
})
onBeforeUnmount(() => observer?.disconnect())
watch([chips, expanded], () => { void nextTick(measure) })
</script>

<style scoped>
.filter-chips {
  display: flex;
  flex-wrap: nowrap;
  align-items: flex-start;
  gap: 2px 4px;
}

.filter-chips__label,
.filter-chips > .q-btn {
  flex: none;
  margin-top: 4px;
}

.filter-chips__list {
  position: relative; /* the chips' offsets are measured from the list */
  display: flex;
  flex: 1 1 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px 4px;
  min-width: 0;
  overflow: hidden;
}

.filter-chips__list > [data-clipped] {
  visibility: hidden;
}

.filter-chips__label {
  font-size: 0.8rem;
  color: rgba(0, 0, 0, 0.65);
  margin-right: 2px;
}

.filter-chips__chip {
  max-width: 100%;
}

.filter-chips__group {
  margin-right: 4px;
  color: rgba(0, 0, 0, 0.65);
}

.filter-chips__value {
  max-width: 18rem;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
</style>
