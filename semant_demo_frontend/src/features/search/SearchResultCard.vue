<template>
  <q-card
    ref="root"
    flat
    bordered
    class="search-result bg-white"
    :class="{ 'search-result--selected': selected, 'citation-target-highlight': highlighted }"
    @dblclick="onDoubleClick"
  >
    <q-card-section class="search-result__header">
      <!-- Only the title row is indented by the checkbox; the rest aligns with the passage. -->
      <div class="search-result__title-row row no-wrap items-start">
        <q-checkbox
          :model-value="selected"
          :aria-label="`Select result ${number}: ${title}`"
          color="primary"
          dense
          class="search-result__select"
          @update:model-value="emit('update:selected', $event)"
        />
        <div class="col search-result__title text-h6 text-primary">
          {{ number }}. {{ title }}
        </div>
        <q-btn
          flat
          dense
          round
          icon="menu_book"
          :color="contextShown ? 'primary' : 'grey-7'"
          :aria-label="`View result ${number} in its document`"
          class="search-result__context"
          data-testid="view-context"
          @click="emit('view-context')"
        >
          <q-tooltip>View in document</q-tooltip>
        </q-btn>
      </div>
      <div class="search-result__meta row text-caption text-grey-8">
        <div><q-icon name="person" class="q-mr-xs"/>{{ chunk.documentObject.author?.join(', ') || 'Unknown Author' }}</div>
        <div><q-icon name="event" class="q-mr-xs"/>{{ chunk.documentObject.yearIssued || 'Year N/A' }}</div>
        <div><q-icon name="language" class="q-mr-xs"/>{{ chunk.language || 'N/A' }}</div>
        <div><q-icon name="description" class="q-mr-xs"/>Pages: {{ chunk.fromPage }}–{{ chunk.toPage }}</div>
      </div>
      <div class="search-result__source text-caption text-grey-8" v-if="chunk.documentObject.title">
        <strong>Source:</strong> {{ chunk.documentObject.title }}
      </div>
      <ResultClassifications :metadata="chunk.metadata" :filters="filters" />
    </q-card-section>

    <q-separator inset />

    <q-card-section class="search-result__body">
      <!-- The complete passage is always in the DOM; a narrow card only clips it to a preview. -->
      <div
        :id="textId"
        ref="textEl"
        class="search-result__text text-body1"
        :class="{ 'search-result__text--preview': preview }"
      >{{ chunk.text }}</div>
      <button
        v-if="constrained && (expanded || clipped)"
        type="button"
        class="search-result__toggle text-primary"
        :aria-expanded="expanded"
        :aria-controls="textId"
        @click="expanded = !expanded"
      >
        {{ expanded ? 'Show less' : 'Show full text' }}
      </button>

      <div class="q-mt-md" v-if="chunk.nerP?.length || chunk.nerG?.length || chunk.nerI?.length || chunk.nerM?.length || chunk.nerO?.length">
        <div class="text-subtitle2 text-grey-7 q-mb-xs">Named Entities</div>
        <div class="row q-gutter-sm">
          <q-badge color="blue-1" text-color="blue-9" class="q-pa-sm" v-if="chunk.nerP?.length">
            <strong>People:</strong>&nbsp;{{ chunk.nerP.join(', ') }}
          </q-badge>
          <q-badge color="green-1" text-color="green-9" class="q-pa-sm" v-if="chunk.nerG?.length">
            <strong>Places:</strong>&nbsp;{{ chunk.nerG.join(', ') }}
          </q-badge>
          <q-badge color="purple-1" text-color="purple-9" class="q-pa-sm" v-if="chunk.nerI?.length">
            <strong>Institutions:</strong>&nbsp;{{ chunk.nerI.join(', ') }}
          </q-badge>
          <q-badge color="orange-1" text-color="orange-9" class="q-pa-sm" v-if="chunk.nerM?.length">
            <strong>Media:</strong>&nbsp;{{ chunk.nerM.join(', ') }}
          </q-badge>
          <q-badge color="grey-2" text-color="grey-9" class="q-pa-sm" v-if="chunk.nerO?.length">
            <strong>Artifacts:</strong>&nbsp;{{ chunk.nerO.join(', ') }}
          </q-badge>
        </div>
      </div>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { QBadge, QBtn, QCard, QCardSection, QCheckbox, QIcon, QSeparator, QTooltip } from 'quasar'
import type { SearchFilter, TextChunkWithDocument } from 'src/generated/api'
import ResultClassifications from './ResultClassifications.vue'
import { isConstrainedResultWidth } from './resultLayout'

const props = withDefaults(defineProps<{
  chunk: TextChunkWithDocument
  /** 1-based position in the whole result list; citations refer to it. */
  number: number
  filters: readonly SearchFilter[]
  selected?: boolean
  highlighted?: boolean
  /** The result is the one shown in the document context view. */
  contextShown?: boolean
}>(), { selected: false, highlighted: false, contextShown: false })

const emit = defineEmits<{
  'update:selected': [value: boolean]
  'view-context': []
}>()

// Double-clicking the card or its text opens the result in its document. Controls keep
// their own behavior: a double-click on the checkbox only toggles it, never opens.
function onDoubleClick (event: MouseEvent) {
  const target = event.target as Element | null
  if (target?.closest('button, a, input, [role="checkbox"]')) return
  emit('view-context')
}

const title = computed(() => props.chunk.queryTitle || props.chunk.title || 'N/A')
const textId = computed(() => `result-text-${props.chunk.id}`)

// A narrow card (narrow window, or both sidebars open) previews the passage; wide cards
// always show all of it. Measured on the card itself, not the viewport.
const root = ref<InstanceType<typeof QCard> | null>(null)
const textEl = ref<HTMLElement | null>(null)
const constrained = ref(false)
const expanded = ref(false) // per result, never part of the search state
const clipped = ref(false)
const preview = computed(() => constrained.value && !expanded.value)

function measure () {
  const card = root.value?.$el as HTMLElement | undefined
  if (card) constrained.value = isConstrainedResultWidth(card.clientWidth)
  // The toggle is offered only when the preview really hides text.
  void nextTick(() => {
    const el = textEl.value
    if (el && preview.value) clipped.value = el.scrollHeight > el.clientHeight + 1
  })
}

let observer: ResizeObserver | null = null
onMounted(() => {
  measure()
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(measure)
    observer.observe(root.value?.$el as HTMLElement)
  }
})
watch(() => props.chunk.text, measure)
onBeforeUnmount(() => observer?.disconnect())
</script>

<style scoped>
.search-result {
  transition: border-color 0.15s, background-color 0.15s;
}

/* Understated: the checkbox stays the state indicator. Uses border/background so it
   never looks like the citation outline or the checkbox's focus ring. */
.search-result--selected {
  border-color: var(--q-primary);
  background-color: #f5f8fd !important;
}

.citation-target-highlight {
  outline: 2px solid var(--q-secondary) !important;
  outline-offset: 0;
}

.search-result__header {
  padding-bottom: 12px;
}

.search-result__select {
  flex: none;
  margin: 2px 8px 0 -4px;
}

.search-result__context {
  flex: none;
  margin: -4px -8px 0 4px;
}

.search-result__title {
  min-width: 0;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.search-result__meta {
  gap: 2px 16px;
  margin-top: 4px;
}

.search-result__source {
  margin-top: 2px;
  overflow-wrap: anywhere;
}

.search-result__text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: #333;
}

.search-result__text--preview {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 6;
  line-clamp: 6;
  overflow: hidden;
}

.search-result__toggle {
  margin-top: 4px;
  padding: 2px 0;
  border: 0;
  background: none;
  font: inherit;
  font-size: 0.875rem;
  cursor: pointer;
}

.search-result__toggle:hover {
  text-decoration: underline;
}

@media (max-width: 599px) {
  .search-result__header,
  .search-result__body {
    padding: 12px;
  }

  .search-result__title {
    font-size: 1.1rem;
  }
}
</style>
