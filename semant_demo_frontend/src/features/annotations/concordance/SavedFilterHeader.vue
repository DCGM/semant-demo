<template>
  <!-- Grows and shrinks smoothly (rows 0fr → 1fr), so the page below glides instead of jumping;
       while closing it keeps showing the saved filter that was open. -->
  <div class="saved-filter-header-wrap" :class="{ 'saved-filter-header-wrap--open': !!active }" :inert="!active || undefined">
    <div class="saved-filter-header-clip">
    <div v-if="shown" class="saved-filter-header" role="region" aria-label="Open saved filter" data-testid="saved-filter-header">
      <!-- Right-aligned: the status and the buttons that come and go stand left of the name, so
           the name and what follows it stay above the saved filters icon. -->
      <span
        class="saved-filter-header__status"
        :class="saved.modified ? 'saved-filter-header__status--changed' : 'text-grey-7'"
        aria-live="polite"
        data-testid="saved-filter-status"
      >
        <template v-if="saved.modified"><span class="saved-filter-header__dot" aria-hidden="true" />Unsaved changes</template>
        <template v-else><q-icon name="check" size="xs" />Filters saved</template>
      </span>
      <span v-if="saved.modified" class="saved-filter-header__actions">
        <q-btn
          flat dense no-caps color="primary" class="saved-filter-header__action" label="Save"
          :disable="!shown.canEdit || busy" data-testid="saved-filter-save"
          @click="save"
        >
          <q-tooltip v-if="!shown.canEdit">Only its creator and the collection owner can save it; save it as a new one instead</q-tooltip>
          <q-tooltip v-else>Save the current filters, order and columns into “{{ shown.name }}” for everyone</q-tooltip>
        </q-btn>
        <q-btn flat dense no-caps color="primary" class="saved-filter-header__action" label="Discard" :disable="busy" data-testid="saved-filter-discard" @click="saved.discard()">
          <q-tooltip>Go back to the filters as saved</q-tooltip>
        </q-btn>
      </span>
      <span class="saved-filter-header__separator" aria-hidden="true" />
      <q-icon name="bookmark" color="primary" size="xs" />
      <span class="saved-filter-header__name text-weight-medium" data-testid="saved-filter-name">{{ shown.name }}</span>
      <q-icon v-if="warning" name="warning" color="warning" size="xs" data-testid="saved-filter-warning">
        <q-tooltip max-width="20rem">{{ warning }}</q-tooltip>
      </q-icon>
      <span class="saved-filter-header__actions">
        <q-btn flat dense no-caps color="primary" class="saved-filter-header__action" label="Save as new…" data-testid="saved-filter-save-as" @click="dialogs.saveAs()" />
        <q-btn flat round dense size="sm" icon="close" aria-label="Close saved filter" data-testid="saved-filter-close" @click="saved.close()">
          <q-tooltip>Close it and go back to the default filters</q-tooltip>
        </q-btn>
      </span>
    </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { QBtn, QIcon, QTooltip } from 'quasar'
import type { Attribute, Tag } from 'src/generated/api'
import { missingReferences, missingText } from './savedFilters'
import { useSavedFilterDialogs } from './useSavedFilterDialogs'
import { useSavedFiltersStore } from './savedFiltersStore'

/** The open saved filter (#824), above the toolbar: its name, whether the filters changed since it
 * was saved, and saving, discarding, saving as new and closing. Shown only while one is open. */
const props = defineProps<{
  tags: Tag[]
  attributes: Attribute[]
}>()

const saved = reactive(useSavedFiltersStore())
const dialogs = useSavedFilterDialogs()
const busy = ref(false)

const active = computed(() => saved.active)
/** The open saved filter, or while the header closes the one that was open. */
const lastActive = ref(saved.active)
watch(active, value => { if (value) lastActive.value = value })
const shown = computed(() => active.value ?? lastActive.value)
const warning = computed(() => {
  const query = active.value?.query
  if (!query || !props.tags.length) return null
  return missingText(missingReferences(query, props.tags, props.attributes))
})

async function save () {
  const item = active.value
  if (!item) return
  busy.value = true
  await dialogs.run(() => saved.update(item.id), `Saved “${item.name}”.`)
  busy.value = false
}
</script>

<style scoped>
.saved-filter-header-wrap {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.45s cubic-bezier(0.22, 1, 0.36, 1);
}
.saved-filter-header-wrap--open { grid-template-rows: 1fr; }
.saved-filter-header-clip { overflow: hidden; min-height: 0; }
@media (prefers-reduced-motion: reduce) {
  .saved-filter-header-wrap { transition: none; }
}
.saved-filter-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  /* Right-aligned, above the saved filters icon it belongs to. */
  justify-content: flex-end;
  gap: 2px 8px;
  min-height: 28px;
  margin-bottom: 4px;
}
.saved-filter-header__name { overflow-wrap: anywhere; }
.saved-filter-header__status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.85rem;
}
.saved-filter-header__status--changed { color: #e65100; font-weight: 500; }
.saved-filter-header__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #f57c00;
}
.saved-filter-header__actions { display: inline-flex; align-items: center; gap: 2px; }
.saved-filter-header__separator { align-self: stretch; margin: 4px 2px; border-left: 1px solid rgba(0, 0, 0, 0.15); }
/* Readable labels without the button's vertical padding: the line stays low. */
.saved-filter-header__action {
  min-height: 26px;
  padding: 0 6px;
  font-size: 0.9rem;
}
.saved-filter-header__action :deep(.q-btn__content) { line-height: 1.2; }
</style>
