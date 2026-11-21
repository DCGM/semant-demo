<template>
  <q-slide-transition>
    <div v-if="active" class="saved-filter-header" role="region" aria-label="Open saved filter" data-testid="saved-filter-header">
      <q-icon name="bookmark" color="primary" size="xs" />
      <span class="saved-filter-header__name text-weight-medium" data-testid="saved-filter-name">{{ active.name }}</span>
      <span
        class="saved-filter-header__status"
        :class="saved.modified ? 'saved-filter-header__status--changed' : 'text-grey-7'"
        aria-live="polite"
        data-testid="saved-filter-status"
      >
        <template v-if="saved.modified"><span class="saved-filter-header__dot" aria-hidden="true" />Unsaved changes</template>
        <template v-else><q-icon name="check" size="xs" />Saved</template>
      </span>
      <q-icon v-if="warning" name="warning" color="warning" size="xs" data-testid="saved-filter-warning">
        <q-tooltip max-width="20rem">{{ warning }}</q-tooltip>
      </q-icon>
      <span class="saved-filter-header__actions">
        <template v-if="saved.modified">
          <q-btn
            flat dense no-caps size="sm" color="primary" label="Save"
            :disable="!active.canEdit || busy" data-testid="saved-filter-save"
            @click="save"
          >
            <q-tooltip v-if="!active.canEdit">Only its creator and the collection owner can save it; save it as a new one instead</q-tooltip>
            <q-tooltip v-else>Save the current filters, order and columns into “{{ active.name }}” for everyone</q-tooltip>
          </q-btn>
          <q-btn flat dense no-caps size="sm" color="primary" label="Discard" :disable="busy" data-testid="saved-filter-discard" @click="saved.discard()">
            <q-tooltip>Go back to the filters as saved</q-tooltip>
          </q-btn>
        </template>
        <q-btn flat dense no-caps size="sm" color="primary" label="Save as new…" data-testid="saved-filter-save-as" @click="dialogs.saveAs()" />
        <q-btn flat round dense size="sm" icon="close" aria-label="Close saved filter" data-testid="saved-filter-close" @click="saved.close()">
          <q-tooltip>Close it and go back to the default filters</q-tooltip>
        </q-btn>
      </span>
    </div>
  </q-slide-transition>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { QBtn, QIcon, QSlideTransition, QTooltip } from 'quasar'
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
.saved-filter-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
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
</style>
