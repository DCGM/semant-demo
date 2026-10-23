<template>
  <!-- Context popover — shows near the mouse when selection or editing -->
  <Teleport to="body">
    <div
      v-if="visible"
      ref="popoverEl"
      class="annotation-popover"
      :class="{ 'is-busy': busy }"
      :style="popoverStyle"
      @mousedown.stop
    >
      <q-btn
        flat dense round
        icon="close"
        size="sm"
        class="popover-close"
        @click="emit('close')"
      />
      <q-linear-progress v-if="busy" indeterminate size="2px" color="primary" class="popover-progress" />

      <!-- Tag picker mode (plain single-pick, or AI multi-select sub-mode) -->
      <template v-if="showTagPicker">
        <div v-if="!isEditing" class="popover-suggest-row">
          <q-btn
            v-if="!showAiTagPicker"
            flat dense no-caps
            icon="auto_awesome"
            label="Suggest tags"
            class="suggest-tags-btn"
            :disable="!tags.length"
            @click="onOpenAiTagPicker"
          >
            <q-tooltip>
              Ask AI to suggest tags for the highlighted text only.
            </q-tooltip>
          </q-btn>
          <q-btn
            v-else
            flat dense round
            icon="arrow_back"
            class="suggest-tags-btn suggest-tags-back"
            aria-label="Back to tag selection"
            @click="showAiTagPicker = false"
          >
            <q-tooltip>Back to tag selection</q-tooltip>
          </q-btn>
        </div>
        <div class="popover-header">
          <span class="popover-title">Select tag</span>
        </div>
        <q-input
          v-model="tagSearch"
          dense
          outlined
          placeholder="Search tags..."
          class="tag-search"
          autofocus
          clearable
        >
          <template #prepend>
            <q-icon name="search" size="xs" />
          </template>
        </q-input>
        <div v-if="showAiTagPicker" class="ai-picker-toolbar">
          <span class="ai-picker-count">
            {{ aiTagPickerSelected.size }} / {{ tags.length }} selected
          </span>
          <q-space />
          <q-btn flat dense no-caps size="sm" label="All" @click="aiPickerSelectAll" />
          <q-btn flat dense no-caps size="sm" label="None" @click="aiPickerSelectNone" />
        </div>
        <div class="tag-list">
          <div
            v-if="!showAiTagPicker"
            class="tag-row tag-row--create"
            @click="emit('createTag')"
          >
            <q-icon name="add_circle_outline" size="16px" class="tag-row-create-icon" />
            <span class="tag-name">Create new tag</span>
          </div>
          <div
            v-for="tag in filteredTags"
            :key="tag.id"
            class="tag-row"
            :class="{
              'is-active': showAiTagPicker
                ? aiTagPickerSelected.has(tag.id)
                : selectedTagId === tag.id,
              'is-suggested': !!suggestionFor(tag.id)
            }"
            @click="showAiTagPicker ? toggleAiPickerTag(tag.id) : emit('pickTag', tag.id)"
          >
            <q-checkbox
              v-if="showAiTagPicker"
              :model-value="aiTagPickerSelected.has(tag.id)"
              dense
              size="xs"
              class="tag-check"
              @click.stop
              @update:model-value="toggleAiPickerTag(tag.id)"
            />
            <q-icon
              v-if="suggestionFor(tag.id)?.score != null"
              name="auto_awesome"
              size="12px"
              class="tag-suggested-icon"
            >
              <q-tooltip>{{ matchPercent(suggestionFor(tag.id)!.score!) }}% match with the selected text</q-tooltip>
            </q-icon>
            <span class="tag-dot" :style="{ backgroundColor: tag.color }"></span>
            <span class="tag-name">{{ tag.name }}</span>
            <span v-if="suggestionFor(tag.id)?.score != null" class="tag-suggested-score">
              {{ matchPercent(suggestionFor(tag.id)!.score!) }}% match
            </span>
            <span v-else-if="suggestionFor(tag.id)" class="tag-suggested-score">Last used</span>
            <span class="tag-shorthand">{{ tag.shorthand }}</span>
          </div>
          <div v-if="filteredTags.length === 0" class="tag-row-empty">No tags found</div>
        </div>
        <div v-if="showAiTagPicker" class="popover-actions ai-picker-actions">
          <q-btn
            no-caps unelevated
            icon="auto_awesome"
            label="Run AI"
            color="primary"
            class="popover-btn"
            :loading="aiSelectionRunning"
            :disable="aiSelectionRunning || aiTagPickerSelected.size === 0"
            @click="emit('runAi', Array.from(aiTagPickerSelected))"
          />
        </div>
      </template>

      <!-- Default action mode -->
      <template v-else>
        <div class="popover-actions">
          <!-- Save position (position changed) — shown first when applicable -->
          <q-btn
            v-if="isEditing && positionChanged"
            no-caps unelevated
            icon="save"
            label="Save position"
            color="primary"
            class="popover-btn"
            :disable="busy"
            @click="emit('savePosition')"
          />
          <!-- Approve / reject shortcut for auto spans (AI suggestions) -->
          <template v-if="editingAuto">
            <q-btn
              no-caps unelevated
              icon="check"
              label="Approve"
              color="positive"
              class="popover-btn"
              :disable="busy"
              @click="emit('approve')"
            />
            <q-btn
              no-caps unelevated
              icon="close"
              label="Reject"
              color="negative"
              class="popover-btn"
              :disable="busy"
              @click="emit('reject')"
            />
          </template>
          <q-btn
            no-caps unelevated
            icon="sell"
            :label="isEditing ? 'Change tag' : 'Add tag'"
            color="primary"
            class="popover-btn"
            @click="showTagPicker = true"
          />
          <q-btn
            v-if="isEditing"
            no-caps outline
            icon="settings"
            label="Tag details"
            color="primary"
            class="popover-btn"
            :disable="!selectedTag"
            @click="emit('tagDetails')"
          />
          <q-btn
            v-if="isEditing"
            no-caps outline
            icon="smart_toy"
            label="Discuss with AI"
            color="info"
            class="popover-btn"
            @click="emit('discuss')"
          />
          <q-btn
            v-if="isEditing"
            no-caps outline
            icon="delete"
            label="Delete"
            color="negative"
            class="popover-btn"
            :disable="busy"
            @click="emit('delete')"
          />
        </div>
      </template>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { Tag } from 'src/generated/api'
import { buildTagSuggestions } from './tagSuggestion'
import { byName } from './tagSortMode'

// The popover for a text selection or an edited span: tag picker, AI tag picker
// ("Suggest tags") and the span actions. The page decides what each action does.
const props = defineProps<{
  visible: boolean
  tags: Tag[]
  /** Changes whenever the selection does; resets the AI tag picker and re-positions. */
  selection: unknown
  /** The text currently highlighted, used to suggest a likely tag first. */
  selectedText: string
  /** The last tag applied in this collection, suggested first regardless of selectedText. */
  lastUsedTagId: string | null
  selectedTagId: string | null
  isEditing: boolean
  positionChanged: boolean
  /** The edited span is an AI suggestion: offer approve and reject. */
  editingAuto: boolean
  /** A span request for this selection is being saved: tags and actions are disabled. */
  busy: boolean
  aiSelectionRunning: boolean
}>()

const emit = defineEmits<{
  close: []
  pickTag: [tagId: string]
  createTag: []
  runAi: [tagIds: string[]]
  savePosition: []
  approve: []
  reject: []
  tagDetails: []
  discuss: []
  delete: []
}>()

const showTagPicker = ref(false)
const tagSearch = ref('')

const selectedTag = computed(() => props.tags.find((t) => t.id === props.selectedTagId) ?? null)

const sortedTags = computed(() =>
  [...props.tags].sort(byName)
)

// Computed lazily (only once the tag list is actually rendered), so this never delays the
// popover opening even for collections with many tags.
const suggestions = computed(() =>
  buildTagSuggestions(props.selectedText, props.tags, props.lastUsedTagId)
)
const suggestionFor = (tagId: string) => suggestions.value.find((s) => s.id === tagId)
const matchPercent = (score: number) => Math.round(score * 100)

const filteredTags = computed(() => {
  const q = (tagSearch.value ?? '').toLowerCase().trim()
  const base = q
    ? sortedTags.value.filter((t) =>
      t.name.toLowerCase().includes(q) || (t.shorthand && t.shorthand.toLowerCase().includes(q))
    )
    : sortedTags.value

  const suggestedIds = suggestions.value.map((s) => s.id)
  const suggested = suggestedIds
    .map((id) => base.find((t) => t.id === id))
    .filter((t): t is Tag => !!t)
  if (!suggested.length) return base

  const suggestedSet = new Set(suggested.map((t) => t.id))
  return [...suggested, ...base.filter((t) => !suggestedSet.has(t.id))]
})

// ── Popover positioning ──
const popoverEl = ref<HTMLElement | null>(null)
const popoverPos = ref({ x: 0, y: 0 })
// Anchor point (mouse coordinates at the time the popover opened) — we keep
// it so we can re-clamp the position when the popover changes size (e.g. the
// user switches into the tag picker or the AI tag picker).
const popoverAnchor = ref<{ x: number; y: number } | null>(null)

const popoverStyle = computed(() => ({
  position: 'fixed' as const,
  left: `${popoverPos.value.x}px`,
  top: `${popoverPos.value.y}px`,
  // Above the header, drawers (3000) and the reader's bulk bar (4000), below the
  // dialogs the popover opens (Quasar $z-fullscreen, 6000), notifications and
  // tooltips, so a dialog covers it while open (#379).
  zIndex: 5000
}))

const POPOVER_VIEWPORT_MARGIN = 8

/**
 * Position the popover relative to the anchor (mouse position) but keep it
 * fully inside the viewport. Default placement is to the bottom-right of the
 * cursor; flip to the left if it would overflow the right edge and flip
 * above the cursor if it would overflow the bottom edge. A final clamp
 * guards against the popover being larger than the remaining space.
 */
function clampPopover() {
  const anchor = popoverAnchor.value
  const el = popoverEl.value
  if (!anchor || !el) return

  const rect = el.getBoundingClientRect()
  const vw = window.innerWidth
  const vh = window.innerHeight
  const m = POPOVER_VIEWPORT_MARGIN

  let x = anchor.x + 12
  let y = anchor.y - 8

  if (x + rect.width + m > vw) {
    x = anchor.x - rect.width - 12
  }
  x = Math.max(m, Math.min(x, vw - rect.width - m))

  if (y + rect.height + m > vh) {
    y = anchor.y - rect.height - 8
  }
  y = Math.max(m, Math.min(y, vh - rect.height - m))

  popoverPos.value = { x, y }
}

/** Anchors the popover at the mouse position of `e`. */
function moveTo(e: MouseEvent) {
  popoverAnchor.value = { x: e.clientX, y: e.clientY }
  // Provisional position; corrected once the popover is rendered/measured.
  popoverPos.value = { x: e.clientX + 12, y: e.clientY - 8 }
  void nextTick(() => clampPopover())
}

/** Opens the tag picker (a fresh selection) or the span actions (an edited span). */
function showMode(mode: 'picker' | 'actions') {
  showTagPicker.value = mode === 'picker'
  showAiTagPicker.value = false
  tagSearch.value = ''
}

// ── AI tag picker ("Suggest tags") ──
// A sub-mode of the tag picker that selects the tags an AI run on the selection
// should consider.
const showAiTagPicker = ref(false)
const aiTagPickerSelected = ref<Set<string>>(new Set())

const onOpenAiTagPicker = () => {
  if (!props.tags.length) return
  // Default to all tags selected — matches the document-wide "AI Tagging"
  // panel, where the user typically wants Topicer to look for everything.
  aiTagPickerSelected.value = new Set(props.tags.map((t) => t.id))
  tagSearch.value = ''
  showAiTagPicker.value = true
}

const toggleAiPickerTag = (tagId: string) => {
  const next = new Set(aiTagPickerSelected.value)
  if (next.has(tagId)) next.delete(tagId)
  else next.add(tagId)
  aiTagPickerSelected.value = next
}

const aiPickerSelectAll = () => {
  aiTagPickerSelected.value = new Set(props.tags.map((t) => t.id))
}

const aiPickerSelectNone = () => {
  aiTagPickerSelected.value = new Set()
}

// Reset the AI picker whenever the selection itself changes — otherwise the
// picker would still be open the next time the user highlights something.
watch(
  () => props.selection,
  () => {
    showAiTagPicker.value = false
  }
)

// Re-clamp the popover whenever its content (and therefore size) changes —
// switching into the tag picker / AI tag picker, or the editing-state of the
// current selection toggling Approve/Reject/Save buttons on or off — and when it
// appears, as it can after being placed while hidden (a failed focused-tag save).
watch(
  [showTagPicker, showAiTagPicker, () => props.selection, () => props.visible],
  () => {
    void nextTick(() => clampPopover())
  }
)

defineExpose({ moveTo, showMode })
</script>

<style scoped>
.annotation-popover {
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 8px;
  padding-top: 28px;
  background: #ffffff;
  border-radius: 10px;
  box-shadow: 0 8px 32px rgba(15, 23, 42, 0.18);
  border: 1px solid rgba(15, 23, 42, 0.08);
  min-width: 180px;
  max-width: 280px;
}

.popover-close {
  position: absolute;
  top: 4px;
  right: 6px;
  z-index: 1;
  font-size: 1.1em;
}

.popover-actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
}

.ai-picker-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  margin-top: 2px;
  font-size: 0.74rem;
  color: #64748b;
}

.ai-picker-count {
  font-weight: 500;
}

.ai-picker-actions {
  margin-top: 4px;
}

.tag-check {
  margin-right: 2px;
}

.popover-btn {
  width: 100%;
  justify-content: flex-start;
  font-size: 0.85rem;
  font-weight: 500;
  min-height: 36px;
  border-radius: 8px;
  padding: 4px 14px;
}

.popover-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  margin-bottom: 2px;
}

.popover-suggest-row {
  position: absolute;
  top: 4px;
  left: 8px;
  z-index: 1;
  height: 22px;
  display: flex;
  align-items: center;
}

.suggest-tags-btn {
  font-size: 0.74rem;
  height: 22px;
  min-height: 22px;
  padding: 0 4px 0 0;
  color: #64748b;
}

.suggest-tags-btn.suggest-tags-back {
  min-width: 22px;
  width: 22px;
  padding: 0;
}

.popover-title {
  font-size: 0.78rem;
  font-weight: 600;
  color: #64748b;
}

.tag-list {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 200px;
  overflow-y: auto;
}

.tag-search {
  width: 100%;
  margin-bottom: 4px;
}

.tag-search :deep(.q-field__control) {
  min-height: 32px;
}

.tag-row-empty {
  padding: 8px;
  text-align: center;
  font-size: 0.78rem;
  color: #94a3b8;
}

.tag-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.12s;
}

.tag-row:hover {
  background: #f1f5f9;
}

/* While the span is being saved, a second pick would be ignored: show the rows as unavailable. */
.annotation-popover.is-busy .tag-row {
  pointer-events: none;
  opacity: 0.5;
}

.popover-progress {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  border-radius: 10px 10px 0 0;
}

.tag-row.is-active {
  background: #e0f2fe;
}

.tag-row.is-suggested {
  border-left: 2px solid #f59e0b;
  padding-left: 6px;
}

.tag-suggested-icon {
  color: #f59e0b;
  flex-shrink: 0;
}

.tag-suggested-score {
  font-size: 0.7rem;
  font-weight: 500;
  color: #b45309;
  flex-shrink: 0;
  white-space: nowrap;
}

.tag-row--create {
  color: #2563eb;
  font-weight: 600;
  border-bottom: 1px solid #e2e8f0;
  margin-bottom: 2px;
  padding-bottom: 7px;
}

.tag-row--create .tag-name {
  color: inherit;
}

.tag-row-create-icon {
  color: #2563eb;
}

.tag-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tag-name {
  font-size: 0.82rem;
  font-weight: 500;
  color: #1e293b;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-shorthand {
  font-size: 0.72rem;
  color: #94a3b8;
  font-weight: 500;
}
</style>
