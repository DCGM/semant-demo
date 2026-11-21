<template>
  <q-btn
    outline
    dense
    color="primary"
    :icon="saved.active ? 'bookmark' : 'bookmark_border'"
    class="saved-filters"
    aria-label="Saved filters"
    data-testid="saved-filters-menu"
  >
    <q-tooltip v-if="!menuOpen">{{ tooltip }}</q-tooltip>
    <q-menu anchor="bottom right" self="top right" @before-show="onShow" @hide="menuOpen = false">
      <q-list class="saved-filters__list q-py-xs">
        <q-item-label header class="row items-center no-wrap">
          <span>Saved filters of this collection</span>
          <q-icon name="info_outline" size="xs" class="q-ml-xs">
            <q-tooltip max-width="20rem">
              A saved filter keeps the filters, order and attribute columns. Opening it lists the annotations that
              match now. Everyone with access to the collection can open it; its creator and the collection owner
              can change it.
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
            <q-item-label class="saved-filters__name">{{ item.name }}</q-item-label>
            <q-item-label caption>
              {{ item.unreadable ? 'Cannot be opened by this version' : `by ${creator(item)}` }}
            </q-item-label>
          </q-item-section>
          <q-item-section v-if="item.canEdit" side>
            <div class="row no-wrap">
              <q-btn flat round dense size="sm" icon="edit" :aria-label="`Rename ${item.name}`" data-testid="saved-filters-rename" @click.stop="dialogs.rename(item)" />
              <q-btn flat round dense size="sm" icon="delete" :aria-label="`Delete ${item.name}`" data-testid="saved-filters-delete" @click.stop="dialogs.remove(item)" />
            </div>
          </q-item-section>
        </q-item>
        <q-separator />
        <q-item v-close-popup clickable data-testid="saved-filters-save" @click="dialogs.saveAs()">
          <q-item-section side class="saved-filters__check"><q-icon name="bookmark_add" color="primary" size="sm" /></q-item-section>
          <q-item-section class="text-primary">Save current filters…</q-item-section>
        </q-item>
      </q-list>
    </q-menu>
  </q-btn>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ClosePopup, QBtn, QIcon, QItem, QItemLabel, QItemSection, QList, QMenu, QSeparator, QTooltip } from 'quasar'
import type { CollectionPerson, SavedSelection } from 'src/generated/api'
import { defaultFilters, useConcordanceStore } from './concordanceStore'
import { liveQueryOf, sameQuery } from './savedFilters'
import { useSavedFilterDialogs } from './useSavedFilterDialogs'
import { useSavedFiltersStore } from './savedFiltersStore'
import { personName } from './provenance'

/** The saved filters of the workspace (#824): an icon next to More filters whose menu opens a
 * saved filter (the open one clicked again closes it), saves the current filters and renames or
 * deletes saved ones. The open saved filter is shown above the toolbar (`SavedFilterHeader`). */
const props = defineProps<{
  collectionId: string
  people: CollectionPerson[]
  /** The signed-in user, named "you". */
  me: string | null
}>()

const vClosePopup = ClosePopup
const saved = reactive(useSavedFiltersStore())
const concordance = useConcordanceStore()
const dialogs = useSavedFilterDialogs()
const menuOpen = ref(false)

const DEFAULT_QUERY = liveQueryOf(defaultFilters(), [])
const tooltip = computed(() => {
  if (saved.active) return 'Saved filters'
  const unsaved = !sameQuery(liveQueryOf(concordance.filters, concordance.shownAttributeIds), DEFAULT_QUERY)
  return unsaved ? 'Saved filters · the current filters are not saved: they last for this session only' : 'Saved filters'
})

function onShow () {
  menuOpen.value = true
  void saved.load(props.collectionId)
}

function creator (item: SavedSelection) {
  return personName(item.createdBy, props.people, props.me)
}

/** Opens the saved filter, or closes it when it is the open one. */
async function toggle (item: SavedSelection) {
  if (concordance.collectionId !== props.collectionId) return
  if (item.id === saved.activeId) await saved.close()
  else await saved.open(item)
}
</script>

<style scoped>
.saved-filters { min-height: 40px; }
/* The divider between More filters and this icon in their group. */
.saved-filters::before { content: ''; position: absolute; left: 0; top: 6px; bottom: 6px; border-left: 1px solid currentColor; opacity: 0.4; }
.saved-filters__list { min-width: 340px; max-width: 440px; }
.saved-filters__check { min-width: 28px; padding-right: 8px; }
.saved-filters__name { overflow-wrap: anywhere; }
</style>
