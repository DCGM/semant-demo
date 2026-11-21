<template>
  <q-btn
    outline
    dense
    no-caps
    color="primary"
    :icon="active ? 'bookmark' : 'bookmark_border'"
    icon-right="arrow_drop_down"
    class="saved-filters"
    :aria-label="active ? `Saved filter: ${active.name}${saved.modified ? ', changed since saved' : ''}` : 'Saved filters'"
    data-testid="saved-filters-menu"
  >
    <span class="saved-filters__label" data-testid="saved-filters-label">{{ active ? active.name : 'Saved filters' }}</span>
    <span v-if="active && saved.modified" class="saved-filters__dot" aria-hidden="true" data-testid="saved-filters-modified" />
    <q-icon v-if="warning" name="warning" color="warning" size="xs" class="q-ml-xs" data-testid="saved-filters-warning-icon" />
    <q-tooltip>{{ tooltip }}</q-tooltip>
    <q-menu anchor="bottom left" self="top left" @before-show="saved.load(collectionId)">
      <q-list dense class="saved-filters__list">
        <q-item-label header class="row items-center no-wrap">
          <span>Saved filters of this collection</span>
          <q-icon name="info_outline" size="xs" class="q-ml-xs">
            <q-tooltip max-width="20rem">
              A saved filter keeps the filters, order and attribute columns. Opening it lists the annotations that
              match now. Everyone with access to the collection can open it; its creator and the collection owner
              can change it. Click the open one again to close it.
            </q-tooltip>
          </q-icon>
        </q-item-label>
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
          @click="toggle(item)"
        >
          <q-item-section side class="saved-filters__check">
            <q-icon v-if="item.id === saved.activeId" name="check" color="primary" size="xs" />
          </q-item-section>
          <q-item-section>
            <q-item-label class="saved-filters__name">
              {{ item.name }}
              <span v-if="item.id === saved.activeId && saved.modified" class="text-grey-7">· changed</span>
            </q-item-label>
            <q-item-label caption>
              {{ item.unreadable ? 'Cannot be opened by this version' : `by ${creator(item)}` }}
            </q-item-label>
            <q-item-label v-if="item.id === saved.activeId && warning" caption class="text-warning" data-testid="saved-filters-warning">
              {{ warning }}
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
        <q-item
          v-if="active && saved.modified && active.canEdit"
          v-close-popup
          clickable
          :disable="busy"
          data-testid="saved-filters-update"
          @click="run(() => saved.update(active!.id), `Saved “${active!.name}”.`)"
        >
          <q-item-section avatar><q-icon name="save" /></q-item-section>
          <q-item-section>Update “{{ active.name }}”</q-item-section>
        </q-item>
        <q-item v-close-popup clickable :disable="busy" data-testid="saved-filters-save" @click="saveAs">
          <q-item-section avatar><q-icon name="bookmark_add" /></q-item-section>
          <q-item-section>Save current filters…</q-item-section>
        </q-item>
      </q-list>
    </q-menu>
  </q-btn>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import {
  ClosePopup, QBtn, QIcon, QItem, QItemLabel, QItemSection, QList, QMenu, QSeparator, QTooltip, useQuasar
} from 'quasar'
import type { Attribute, CollectionPerson, SavedSelection, Tag } from 'src/generated/api'
import { defaultFilters, useConcordanceStore } from './concordanceStore'
import { liveQueryOf, missingReferences, missingText, sameQuery } from './savedFilters'
import { useSavedFiltersStore } from './savedFiltersStore'
import { personName } from './provenance'

/** The saved filters of the workspace (#824) in one toolbar button: it names the open saved filter
 * (a dot when the filters changed since), and its menu opens, closes (the open one clicked again),
 * saves, updates, renames and deletes them. Filters not saved last for this session only. */
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
/** Filters other than the defaults that no saved filter holds. */
const unsaved = computed(() => !active.value && !sameQuery(liveQueryOf(concordance.filters, concordance.shownAttributeIds), DEFAULT_QUERY))
const tooltip = computed(() => {
  if (active.value) {
    return saved.modified
      ? `Saved filter “${active.value.name}”, changed since saved: the changes last for this session only`
      : `Saved filter “${active.value.name}”`
  }
  return unsaved.value ? 'The current filters are not saved: they last for this session only' : 'Open or save filters of this collection'
})
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
  askName('Save current filters', active.value?.name ? `${active.value.name} (copy)` : '', 'Save',
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

/** Opens the saved filter, or closes it when it is the open one. */
async function toggle (item: SavedSelection) {
  if (concordance.collectionId !== props.collectionId) return
  if (item.id === saved.activeId) await saved.close()
  else await saved.open(item)
}
</script>

<style scoped>
.saved-filters { min-height: 40px; flex: 0 1 auto; max-width: 16rem; }
.saved-filters__label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.saved-filters__dot {
  width: 7px;
  height: 7px;
  margin-left: 4px;
  border-radius: 50%;
  background: currentColor;
  flex: 0 0 auto;
}
.saved-filters__list { min-width: 300px; max-width: 420px; }
.saved-filters__check { min-width: 20px; padding-right: 4px; }
.saved-filters__name { overflow-wrap: anywhere; }
</style>
