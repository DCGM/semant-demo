<template>
  <div class="saved-filters" role="region" aria-label="Saved filters" data-testid="saved-filters">
    <q-icon name="bookmarks" size="xs" color="grey-7" />
    <div class="saved-filters__status" aria-live="polite" data-testid="saved-filters-status">
      <template v-if="active">
        <span class="text-grey-8">Live filter:</span>
        <span class="text-weight-medium" data-testid="saved-filters-active">{{ active.name }}</span>
        <q-badge outline color="primary" label="Live" data-testid="saved-filters-live">
          <q-tooltip>Evaluated again every time it is opened: it lists the annotations that match now, not a fixed set</q-tooltip>
        </q-badge>
        <span v-if="saved.modified" class="text-grey-8" data-testid="saved-filters-modified">
          · changed, not saved (this session only)
        </span>
      </template>
      <span v-else-if="unsaved" class="text-grey-8" data-testid="saved-filters-unsaved">
        Unsaved filters · kept for this session only
      </span>
    </div>
    <q-btn
      v-if="active && saved.modified && active.canEdit"
      flat dense no-caps color="primary" icon="save" label="Update"
      :loading="busy" data-testid="saved-filters-update"
      @click="run(() => saved.update(active!.id), `Saved “${active!.name}”.`)"
    >
      <q-tooltip>Save the current filters, order and columns into “{{ active.name }}”</q-tooltip>
    </q-btn>
    <q-btn
      v-if="unsaved || (active && saved.modified)"
      flat dense no-caps color="primary" icon="bookmark_add" label="Save as…"
      :disable="busy" data-testid="saved-filters-save"
      @click="saveAs"
    >
      <q-tooltip>Save the current filters, order and columns as a live filter of this collection, shared with its members</q-tooltip>
    </q-btn>
    <q-btn flat dense no-caps color="primary" icon-right="arrow_drop_down" :label="menuLabel" data-testid="saved-filters-menu">
      <q-menu anchor="bottom right" self="top right" @before-show="saved.load(collectionId)">
        <q-list style="min-width: 300px; max-width: 420px" dense>
          <q-item-label header>Saved live filters of this collection</q-item-label>
          <q-item v-if="saved.error" data-testid="saved-filters-error">
            <q-item-section class="text-negative">{{ saved.error }}</q-item-section>
          </q-item>
          <q-item v-else-if="!saved.items.length && !saved.loading" data-testid="saved-filters-empty">
            <q-item-section class="text-grey-7">No saved filters yet.</q-item-section>
          </q-item>
          <q-item
            v-for="item in saved.items"
            :key="item.id"
            v-close-popup
            clickable
            :active="item.id === saved.activeId"
            :disable="item.unreadable"
            data-testid="saved-filters-item"
            @click="open(item)"
          >
            <q-item-section>
              <q-item-label class="saved-filters__name">{{ item.name }}</q-item-label>
              <q-item-label caption>
                {{ item.unreadable ? 'Cannot be opened by this version' : `Live · by ${creator(item)}` }}
              </q-item-label>
            </q-item-section>
            <q-item-section v-if="item.canEdit" side>
              <div class="row no-wrap">
                <q-btn flat round dense size="sm" icon="edit" :aria-label="`Rename ${item.name}`" data-testid="saved-filters-rename" @click.stop="rename(item)" />
                <q-btn flat round dense size="sm" icon="delete" :aria-label="`Delete ${item.name}`" data-testid="saved-filters-delete" @click.stop="remove(item)" />
              </div>
            </q-item-section>
          </q-item>
          <q-separator />
          <q-item v-close-popup clickable :disable="busy" data-testid="saved-filters-save-menu" @click="saveAs">
            <q-item-section avatar><q-icon name="bookmark_add" /></q-item-section>
            <q-item-section>Save current filters as…</q-item-section>
          </q-item>
          <q-item-label caption class="q-px-md q-pb-sm text-grey-7">
            Everyone with access to the collection sees and opens them; their creator and the collection owner can change them.
          </q-item-label>
        </q-list>
      </q-menu>
    </q-btn>
  </div>
  <div v-if="warning" class="saved-filters__warning text-warning q-mb-sm" role="status" data-testid="saved-filters-warning">
    <q-icon name="warning" size="xs" /> {{ warning }}
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import {
  ClosePopup, QBadge, QBtn, QIcon, QItem, QItemLabel, QItemSection, QList, QMenu, QSeparator, QTooltip, useQuasar
} from 'quasar'
import type { Attribute, CollectionPerson, SavedSelection, Tag } from 'src/generated/api'
import { defaultFilters, useConcordanceStore } from './concordanceStore'
import { liveQueryOf, missingReferences, missingText, sameQuery } from './savedFilters'
import { useSavedFiltersStore } from './savedFiltersStore'
import { personName } from './provenance'

/** Saved live filters of the workspace (#824): which one is shown and whether it changed, the
 * unsaved filters labeled as kept for this session only, and the collection's saved filters to
 * open, save, update, rename and delete. */
const props = defineProps<{
  collectionId: string
  tags: Tag[]
  attributes: Attribute[]
  people: CollectionPerson[]
  /** The signed-in user, named "you". */
  me: string | null
}>()

const vClosePopup = ClosePopup
const $q = useQuasar()
const saved = reactive(useSavedFiltersStore())
const concordance = useConcordanceStore()
const busy = ref(false)

const active = computed(() => saved.active)
const DEFAULT_QUERY = liveQueryOf(defaultFilters(), [])
/** Filters other than the defaults that no saved filter holds: they last for this session only. */
const unsaved = computed(() => !active.value && !sameQuery(liveQueryOf(concordance.filters, concordance.shownAttributeIds), DEFAULT_QUERY))
const menuLabel = computed(() => saved.items.length ? `Saved filters (${saved.items.length})` : 'Saved filters')
const warning = computed(() => {
  const query = active.value?.query
  if (!query || !props.tags.length) return null
  return missingText(missingReferences(query, props.tags, props.attributes))
})

function creator (item: SavedSelection) {
  return personName(item.createdBy, props.people, props.me)
}

async function run (write: () => Promise<void>, done: string) {
  busy.value = true
  try {
    await write()
    $q.notify({ type: 'positive', message: done })
  } catch (e) {
    $q.notify({ type: 'negative', message: e instanceof Error ? e.message : String(e) })
  } finally {
    busy.value = false
  }
}

function askName (title: string, value: string, ok: string, then: (name: string) => Promise<void>) {
  $q.dialog({
    title,
    prompt: { model: value, type: 'text', isValid: (v: string) => !!v.trim() && v.trim().length <= 200, counter: true, maxlength: 200 },
    ok: { label: ok, color: 'primary', unelevated: true },
    cancel: { flat: true, color: 'primary' },
    persistent: false
  }).onOk((name: string) => { void then(name.trim()) })
}

function saveAs () {
  askName('Save filters as a live filter', active.value?.name ? `${active.value.name} (copy)` : '', 'Save',
    name => run(() => saved.saveAs(name), `Saved “${name}”.`))
}

function rename (item: SavedSelection) {
  askName('Rename saved filter', item.name, 'Rename', name => run(() => saved.rename(item.id, name), `Renamed to “${name}”.`))
}

function remove (item: SavedSelection) {
  $q.dialog({
    title: 'Delete saved filter',
    message: `Delete “${item.name}” for everyone in this collection? No annotations change.`,
    ok: { label: 'Delete', color: 'negative', unelevated: true },
    cancel: { flat: true, color: 'primary' }
  }).onOk(() => { void run(() => saved.remove(item.id), `Deleted “${item.name}”.`) })
}

async function open (item: SavedSelection) {
  if (concordance.collectionId !== props.collectionId) return
  await saved.open(item)
}
</script>

<style scoped>
.saved-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  min-height: 32px;
}
.saved-filters__status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
  flex: 1 1 12rem;
  min-width: 0;
  overflow-wrap: anywhere;
}
.saved-filters__name { overflow-wrap: anywhere; }
.saved-filters__warning { display: flex; align-items: center; gap: 4px; }
</style>
