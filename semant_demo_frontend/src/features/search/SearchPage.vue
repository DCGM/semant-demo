<template>
  <q-page :class="resultsState === 'idle' ? 'q-pa-md bg-grey-1 flex flex-center' : 'q-pa-md bg-grey-1'">
    <div style="width: 100%; max-width: 1400px; margin: 0 auto;">

      <q-card flat bordered class="q-mb-xl bg-white">
        <q-form @submit.prevent="onSearch">
          <q-card-section>
            <div class="row q-col-gutter-sm items-center">
              <div class="col relative-position">
                <!-- Recent searches (#558) open under the input when it is focused by the user,
                     clicked or typed into; not on the page's own autofocus. Only typing
                     narrows them: opened, they list the whole recent history. -->
                <q-input
                  v-model="queryInput"
                  dense
                  outlined
                  required
                  autofocus
                  autocomplete="off"
                  aria-label="Search query"
                  role="combobox"
                  aria-autocomplete="list"
                  :aria-expanded="history.shown.value"
                  :aria-controls="history.shown.value && historyItems.length ? HISTORY_LIST_ID : undefined"
                  :aria-activedescendant="activeHistoryOptionId"
                  data-testid="search-query"
                  @keydown="onQueryKeydown"
                  @focus="onQueryFocus"
                  @click="history.show"
                  @blur="history.close"
                  @update:model-value="history.onInput"
                >
                  <template v-slot:prepend>
                    <q-btn
                      type="submit"
                      color="primary"
                      icon="search"
                      round
                      flat
                      dense
                      aria-label="Search"
                      :loading="loading"
                      @click="onSearch"
                    />
                  </template>
                </q-input>
                <SearchHistoryDropdown
                  v-if="history.shown.value"
                  :items="historyItems"
                  :active-index="history.activeIndex.value"
                  :list-id="HISTORY_LIST_ID"
                  :note="historyNote"
                  :newer-format="history.newerFormat.value"
                  @choose="chooseHistory"
                  @remove="removeHistory"
                  @highlight="history.activeIndex.value = $event"
                  @clear="clearHistory"
                />
              </div>

              <div class="col-auto">
                <q-btn
                  flat
                  color="primary"
                  icon="tune"
                  aria-label="Search filters"
                  :aria-expanded="showFilters"
                  @click="showFilters = !showFilters"
                />
              </div>
            </div>

            <!-- Changes in the form are a draft until Enter or Search applies them; the results
                 and the chips below stay those of the applied search. -->
            <div
              v-if="pending && applied.criteria.textQuery"
              class="row no-wrap items-center q-mt-xs text-caption text-grey-8 pending-note"
              role="status"
              data-testid="search-pending"
            >
              <q-icon name="edit_note" size="18px" class="q-mr-xs" />
              <span class="col">Changes not applied yet. Press Enter or Search to apply them.</span>
              <q-btn flat dense no-caps size="sm" color="primary" label="Discard changes" @click="discardDraft" />
            </div>

            <div v-if="appliedChips.length" class="row q-gutter-sm q-mt-sm" aria-label="Applied filters">
              <q-chip
                v-for="chip in appliedChips"
                :key="chip.key"
                removable
                color="primary"
                text-color="white"
                class="active-filter-chip"
                :aria-label="chip.label"
                @remove="removeChip(chip)"
              >
                <q-icon :name="chip.icon" size="16px" class="q-mr-xs" />
                {{ chip.label }}
              </q-chip>
            </div>
          </q-card-section>

          <q-slide-transition>
            <div v-show="showFilters">
              <div class="relative-position q-pt-sm">
                <q-separator inset />
                <div class="absolute bg-white q-px-sm" style="z-index: 1; bottom: 0; left: 50%; transform: translate(-50%, 50%);" v-if="draftHasFilters">
                  <q-btn
                    outline
                    dense
                    color="negative"
                    @click="clearAllFilters"
                    class="bg-white q-px-sm"
                  >
                    <div class="row items-center no-wrap" style="line-height: 1;">
                      <q-icon name="delete" size="16px" class="q-mr-xs" />
                      <span>Clear Filters</span>
                    </div>
                  </q-btn>
                </div>
              </div>
              <q-card-section class="bg-grey-1" :style="draftHasFilters ? 'padding-top: 24px;' : ''">
                <div class="row q-col-gutter-md">

                  <div v-if="userStore.isLoggedIn" class="col-12 col-sm-6 col-md-4">
                    <q-select
                      v-model="draftCollection"
                      :options="collectionOptions"
                      label="Select a Collection"
                      outlined
                      dense
                      emit-value
                      map-options
                      clearable
                      :loading="collectionsLoading"
                    >
                      <template v-slot:prepend>
                        <q-icon name="folder" />
                      </template>
                    </q-select>
                  </div>

                  <!-- Configured search vectors (embedding models); offered only when there is a choice. -->
                  <div v-if="vectorOptions.length > 1" class="col-12 col-sm-6 col-md-4">
                    <q-select
                      v-model="selectedVector"
                      :options="vectorOptions"
                      label="Embedding model"
                      outlined
                      dense
                      emit-value
                      map-options
                      data-testid="search-vector-select"
                    >
                      <template v-slot:prepend>
                        <q-icon name="hub" />
                      </template>
                      <template v-slot:option="scope">
                        <q-item v-bind="scope.itemProps">
                          <q-item-section>
                            <q-item-label>{{ scope.opt.label }}</q-item-label>
                            <q-item-label v-if="scope.opt.description" caption>{{ scope.opt.description }}</q-item-label>
                          </q-item-section>
                        </q-item>
                      </template>
                    </q-select>
                  </div>

                  <div v-if="loadingFilters" class="col-12 text-caption text-grey flex items-center q-pa-sm">
                    <q-spinner color="primary" size="1.5em" class="q-mr-sm" />
                    Loading available search filters...
                  </div>
                  <template v-else>
                    <div
                      v-for="filter in offeredFilters"
                      :key="filter.id"
                      class="col-12 col-sm-6 col-md-4"
                    >
                      <!-- Interval Filter: the publication year -->
                      <div v-if="filter.type === 'interval'">
                        <div class="row items-center text-subtitle2 q-mb-xs text-grey-8">
                          <q-icon :name="getFilterIcon(filter.id)" size="18px" class="q-mr-xs" />
                          <span>{{ formatFilterLabel(filter.id) }}: {{ draftYearRange(filter).min }} - {{ draftYearRange(filter).max }}</span>
                        </div>
                        <div class="q-px-sm">
                          <q-range
                            :model-value="draftYearRange(filter)"
                            :min="intervalBounds(filter).min"
                            :max="intervalBounds(filter).max"
                            :step="1"
                            label
                            color="primary"
                            @update:model-value="setDraftYearRange(filter, $event)"
                          />
                        </div>
                      </div>

                      <!-- Nominal Filter: passage language and classifications -->
                      <div v-else>
                        <q-select
                          :model-value="draftNominal(filter)"
                          :options="getNominalOptions(filter)"
                          :label="formatFilterLabel(filter.id)"
                          multiple
                          use-chips
                          outlined
                          dense
                          emit-value
                          map-options
                          clearable
                          @update:model-value="setDraftNominal(filter, $event)"
                        >
                          <template v-slot:prepend>
                            <q-icon :name="getFilterIcon(filter.id)" />
                          </template>
                        </q-select>
                      </div>
                    </div>
                  </template>

                </div>
              </q-card-section>
            </div>
          </q-slide-transition>

        </q-form>
      </q-card>

      <div v-if="resultsState === 'loading'" class="results-status column items-center q-pa-xl text-grey-8" role="status" data-testid="search-loading">
        <q-spinner color="primary" size="2.5em" />
        <div class="q-mt-sm">Searching passages…</div>
      </div>

      <q-banner v-else-if="resultsState === 'error'" rounded class="bg-red-1 text-negative" role="alert" data-testid="search-error">
        <template v-slot:avatar>
          <q-icon name="error_outline" color="negative" />
        </template>
        Search failed: {{ passages.error.value }}
        <template v-slot:action>
          <q-btn flat color="negative" label="Try again" @click="runApplied" />
        </template>
      </q-banner>

      <div v-else-if="resultsState === 'empty'" class="results-status column items-center q-pa-xl text-grey-8" role="status" data-testid="search-empty">
        <q-icon name="search_off" size="2.5em" />
        <div class="q-mt-sm text-subtitle1">No passages match this search.</div>
        <div class="text-caption">Try other words, or remove some of the filters above.</div>
      </div>

      <div v-else-if="resultsState === 'needsQuery'" class="results-status column items-center q-pa-xl text-grey-8" role="status" data-testid="search-needs-query">
        <q-icon name="manage_search" size="2.5em" />
        <div class="q-mt-sm text-subtitle1">Enter a text query to search passages with these filters.</div>
        <div class="text-caption">Browsing documents by filters alone is not available here yet.</div>
      </div>

      <div v-else-if="resultsState === 'results'">
        <div class="row items-end justify-between q-mb-md">
          <div>
            <div class="text-h5 text-weight-medium">Passages</div>
            <div class="text-caption text-grey-7" data-testid="search-coverage">
              {{ coverage }} Search completed in {{ timeSpent.toFixed(2) }}s.
            </div>
          </div>
        </div>

        <q-slide-transition>
          <div v-show="selectedResults.length > 0" class="q-mb-lg">
            <q-card flat bordered class="bg-primary text-white">
              <q-card-section class="selection-toolbar q-pa-sm">
                <div class="row items-center no-wrap">
                  <div class="text-subtitle2 q-ml-sm col" aria-live="polite">{{ selectedResults.length }} item(s) selected</div>
                  <q-btn flat color="white" icon="close" label="Clear selection" @click="clearSelection" />
                </div>
                <!-- Collection membership: signed-in users with a collection they may edit (the backend checks again). -->
                <div v-if="canAddToCollections" class="selection-toolbar__actions">
                  <q-select
                    v-model="targetCollectionId"
                    :options="targetCollectionOptions"
                    label="Select Collection"
                    dense
                    outlined
                    dark
                    emit-value
                    map-options
                    class="selection-toolbar__collection"
                  />
                  <q-btn flat color="white" icon="library_add" label="Add Chunks" @click="addSelectedChunksToCollection" />
                  <q-btn flat color="white" icon="post_add" label="Add Documents" @click="addSelectedDocumentsToCollection" />
                </div>
              </q-card-section>
            </q-card>
          </div>
        </q-slide-transition>

        <div class="q-gutter-y-md">
          <SearchResultCard
            v-for="(chunk, index) in results"
            :id="`result-${index + 1}`"
            :key="chunk.id"
            :chunk="chunk"
            :number="index + 1"
            :filters="availableSearchFilters"
            :selected="selectedResults.includes(chunk.id)"
            :highlighted="highlightedDocNumber === index + 1"
            :context-shown="contextResultNumber === index + 1"
            @update:selected="setSelected(chunk.id, $event)"
            @view-context="viewContext(chunk, index + 1)"
          />
        </div>

        <div class="column items-center q-mt-xl q-gutter-y-sm">
          <q-banner v-if="passages.loadMoreError.value" dense rounded class="bg-red-1 text-negative" role="alert">
            {{ passages.loadMoreError.value }}
          </q-banner>
          <q-btn
            v-if="hasMore"
            outline
            color="primary"
            icon="expand_more"
            label="Load more passages"
            :loading="passages.loadingMore.value"
            data-testid="search-load-more"
            @click="passages.loadMore"
          />
        </div>
      </div>

    </div>

    <RightSidebarPanel v-if="results.length || loading" id="search-summary" label="Summary" icon="summarize">
      <SearchSummaryPanel
        :tokens="searchSummary.tokens"
        :time-spent="searchSummary.timeSpent"
        v-model:length="searchSummary.length"
        v-model:scope="searchSummary.scope"
        :error="searchSummary.error"
        :loading="searchSummary.summarizing"
        :disable="!results.length"
        @summarize="searchSummary.summarize"
        @cite="jumpToResult"
      />
    </RightSidebarPanel>

    <!-- Registered once a result is opened, so the Summary stays the default panel. -->
    <RightSidebarPanel v-if="contextResultNumber !== null" :id="CONTEXT_PANEL_ID" label="Document" icon="menu_book" :order="1">
      <ChunkContextPanel
        :target-chunk-id="chunkContext.target?.chunkId ?? null"
        :document="chunkContext.document"
        :chunks="chunkContext.chunks"
        :has-before="chunkContext.hasBefore"
        :has-after="chunkContext.hasAfter"
        :focus-request="chunkContext.focusRequest"
        :loading="chunkContext.loading"
        :extending="chunkContext.extending"
        :error="chunkContext.error"
        :open-link="chunkContext.target ? documentLink(chunkContext.target.documentId, { chunkId: chunkContext.target.chunkId, from: 'search' }) : null"
        return-label="Focus on result"
        @extend="chunkContext.extend"
        @reload="chunkContext.load"
        @return="returnToContextResult"
      />
    </RightSidebarPanel>
  </q-page>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { ref, computed, onMounted, nextTick, onBeforeUnmount, reactive, shallowRef, watch } from 'vue'
import { QPage, QForm, QInput, QBtn, QCard, QCardSection, QSeparator, QSelect, QRange, QItem, QItemSection, QItemLabel, QBanner, QSpinner, Notify, useQuasar } from 'quasar'
import { SearchType, WriteOutcome, type SearchFilter, type SearchVectorInfo } from 'src/generated/api'
import { captureSession, useApi } from 'src/shared/api'
import { useUserStore } from 'src/features/auth/userStore'
import { useUserCollectionsStore } from 'src/features/user_collections/userCollectionsStore'
import { useDocumentsStore } from 'src/features/documents/documentsStore'
import { collectionRights } from 'src/features/user_collections/permissions'
import { emptyCriteria, emptyLocation, MAX_TEXT_QUERY_LENGTH, normalizeCriteria, sameCriteria, hasFilters, type Criteria, type ExploreLocation } from 'src/features/explore/criteria'
import { useExploreLocation, type AppliedReason } from 'src/features/explore/useExploreLocation'
import { hasMorePassages, passageCoverage, usePassageSearch } from 'src/features/explore/usePassageSearch'
import { useSearchSummary } from './useSearchSummary'
import SearchSummaryPanel from './SearchSummaryPanel.vue'
import SearchResultCard from './SearchResultCard.vue'
import { escapeClearsSelection } from './resultLayout'
import type { SearchResultsContext } from './searchResults'
import {
  criteriaChips, criteriaOfFilterValues, filterTarget, formatFilterLabel, historyFiltersOf, intervalBounds,
  nominalValuesOf, offeredCriteria, withNominalValues, withYearRange, yearRangeOf, type CriterionChip, type IntervalValue
} from './searchFilters'
import { criteriaOfRequest, describeCriteria, restoreSearch, searchHistoryCriteria, type SearchHistoryCriteria, type SearchOptions } from './searchHistoryCriteria'
import SearchHistoryDropdown from 'src/shared/searchHistory/SearchHistoryDropdown.vue'
import { useSearchHistory } from 'src/shared/searchHistory/useSearchHistory'
import { entryKey, MAX_QUERY_LENGTH, type HistoryAudience, type HistoryEntry, type SearchHistoryItem } from 'src/shared/searchHistory/history'
import RightSidebarPanel from 'src/app/sidebar/RightSidebarPanel.vue'
import { useRightSidebarStore } from 'src/app/sidebar/rightSidebarStore'
import ChunkContextPanel from 'src/features/documents/ChunkContextPanel.vue'
import { whileShown } from 'src/shared/whileShown'
import { documentLink } from 'src/features/documents/workspace/documentLink'
import { useChunkContext } from 'src/features/documents/useChunkContext'

// The Search page is being evolved into Explore Results (#605, docs/EXPLORATION.md): it edits
// draft search criteria, and Enter or Search applies them. The applied criteria, the search
// vector and the results mode live in the URL (`features/explore`), so Back/Forward and shared
// links restore a search; the collection scope is a page setting, never in the URL. Results are
// Passages (`POST /api/search/passages`), loaded page by page; Documents follow in #527b/c.

const api = useApi().default

// Draft: what the form shows. Nothing is searched until it is applied.
const showFilters = ref(false)
const queryInput = ref('')
const draftFilters = ref<Criteria>(emptyCriteria())
const draftVector = ref<string | null>(null) // null: the configured default
const draftCollection = ref<string | null>(null)
const draftCriteria = computed(() => normalizeCriteria({ ...draftFilters.value, textQuery: queryInput.value }))

// Applied: the URL's location (`explore`, set up below once everything it runs exists), and the
// collection scope it was applied with.
const appliedCollection = ref<string | null>(null)
const applied = shallowRef<ExploreLocation>(emptyLocation())

const pending = computed(() => !sameCriteria(draftCriteria.value, applied.value.criteria) ||
  draftVector.value !== applied.value.vector || draftCollection.value !== appliedCollection.value)

// Search vectors (GET /api/search/vectors): null in the request means the server's default,
// so choosing the default again sends no explicit selection.
const availableVectors = ref<SearchVectorInfo[]>([])
const defaultVector = ref<string | null>(null)
const vectorOptions = computed(() => availableVectors.value.map(v => ({
  label: v.id === defaultVector.value ? `${v.name} (default)` : v.name,
  value: v.id,
  description: v.description
})))
const selectedVector = computed<string | null>({
  get: () => draftVector.value ?? defaultVector.value,
  set: (id) => { draftVector.value = id === defaultVector.value ? null : id }
})

// Configured search filters: widgets editing the draft criteria (searchFilters.ts).
const loadingFilters = ref(false)
const availableSearchFilters = ref<SearchFilter[]>([])
const offeredFilters = computed(() => availableSearchFilters.value.filter(f => filterTarget(f) !== null))

function getFilterIcon (id: string): string {
  if (id === 'language') return 'language'
  if (id.includes('year') || id.includes('date') || id.includes('period')) return 'event'
  if (id.includes('mode') || id.includes('interactivity')) return 'forum'
  if (id.includes('type') || id.includes('genre')) return 'category'
  return 'filter_list'
}

function getNominalOptions (filter: SearchFilter) {
  if (!filter.values) return []
  return filter.values.map(v => ({
    label: v.userForm,
    value: v.backendForm
  }))
}

const draftYearRange = (filter: SearchFilter) => yearRangeOf(draftFilters.value, filter)
const setDraftYearRange = (filter: SearchFilter, range: IntervalValue | null) => {
  draftFilters.value = withYearRange(draftFilters.value, filter, range ?? intervalBounds(filter))
}
const draftNominal = (filter: SearchFilter) => nominalValuesOf(draftFilters.value, filter)
const setDraftNominal = (filter: SearchFilter, values: string[] | null) => {
  draftFilters.value = withNominalValues(draftFilters.value, filter, values)
}

// Results: the passages of the applied search, as loaded so far.
const passages = usePassageSearch()
const loading = passages.loading
const results = computed(() => passages.results.value?.items ?? [])
const timeSpent = computed(() => passages.results.value?.timeSpent ?? 0)
const coverage = computed(() => (passages.results.value ? passageCoverage(passages.results.value) : ''))
const hasMore = computed(() => (passages.results.value ? hasMorePassages(passages.results.value) : false))
const searchContext = computed<SearchResultsContext | null>(() => {
  const current = passages.results.value
  return current
    ? { id: current.id, query: current.query.criteria.textQuery ?? '', results: current.items, timeSpent: current.timeSpent }
    : null
})
const selectedResults = ref<string[]>([])
const targetCollectionId = ref<string | null>(null)

/** What the results area shows besides result cards. */
const resultsState = computed<'results' | 'loading' | 'error' | 'empty' | 'needsQuery' | 'idle'>(() => {
  if (loading.value) return 'loading'
  if (passages.error.value) return 'error'
  if (passages.results.value) return results.value.length ? 'results' : 'empty'
  if (!applied.value.criteria.textQuery && hasFilters(applied.value.criteria)) return 'needsQuery'
  return 'idle'
})

function clearSelection () {
  selectedResults.value = []
}

// Escape clears the whole selection unless a field or overlay needs it.
function onKeydown (event: KeyboardEvent) {
  if (selectedResults.value.length && escapeClearsSelection(event)) clearSelection()
}

function setSelected (chunkId: string, selected: boolean) {
  const others = selectedResults.value.filter(id => id !== chunkId)
  selectedResults.value = selected ? [...others, chunkId] : others
}

// Summarization (right sidebar): works on the loaded results or the selected ones
const searchSummary = reactive(useSearchSummary(searchContext, selectedResults))

// Citations
const highlightedDocNumber = ref<number | null>(null)
let clearHighlightTimer: number | null = null

async function jumpToResult (docNumber: number) {
  const resultIndex = docNumber - 1
  if (resultIndex < 0 || resultIndex >= results.value.length) {
    Notify.create({ message: `Result [${docNumber}] is not available.`, position: 'top', color: 'warning' })
    return
  }
  await nextTick()

  highlightedDocNumber.value = docNumber
  if (clearHighlightTimer !== null) {
    window.clearTimeout(clearHighlightTimer)
  }
  clearHighlightTimer = window.setTimeout(() => {
    highlightedDocNumber.value = null
    clearHighlightTimer = null
  }, 1600)

  const target = document.getElementById(`result-${docNumber}`)
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' })
  }
}

// Document context (right sidebar): one result shown in its document
const CONTEXT_PANEL_ID = 'search-context'
const $q = useQuasar()
const rightSidebar = useRightSidebarStore()
const chunkContext = reactive(useChunkContext())
const contextResultNumber = ref<number | null>(null)

async function viewContext (chunk: { document: string, id: string }, number: number) {
  contextResultNumber.value = number
  const opening = chunkContext.open({ documentId: chunk.document, chunkId: chunk.id })
  await nextTick() // the panel registers when the first result is opened
  rightSidebar.activate(CONTEXT_PANEL_ID)
  await opening
}

async function returnToContextResult () {
  if (contextResultNumber.value === null) return
  // On narrow screens the sidebar covers the results.
  if ($q.screen.lt.md) rightSidebar.open = false
  await jumpToResult(contextResultNumber.value)
}

// The shown result belongs to one search: another search (or none) closes it and its
// panel, so the view never shows a result that is no longer in the list. Loading more keeps it.
watch(() => passages.results.value?.id, () => {
  chunkContext.clear()
  contextResultNumber.value = null
})

// Collections & User State
const userStore = useUserStore()
const collectionsStore = useUserCollectionsStore()
const { collections, loading: collectionsLoading } = storeToRefs(collectionsStore)
const { fetchCollections } = collectionsStore
const documentsStore = useDocumentsStore()

// Whether the user's collections were loaded for the search history (the store's own
// loading/error flags are shared with other requests).
const collectionsLoad = ref<{ userId: string, status: 'loading' | 'ready' | 'failed' } | null>(null)

async function loadCollections () {
  const userId = userStore.getUserId
  if (!userStore.isLoggedIn || !userId) return
  collectionsLoad.value = { userId: String(userId), status: 'loading' }
  await fetchCollections()
  if (collectionsLoad.value?.userId !== String(userId) || userStore.getUserId !== userId) return
  collectionsLoad.value = { userId: String(userId), status: collectionsStore.error ? 'failed' : 'ready' }
}

watch(
  () => userStore.getUserId,
  async (userId, previousUserId) => {
    if (previousUserId && userId !== previousUserId) {
      // Signed out or another user: results and selections may come from the previous
      // user's collections.
      passages.cancel()
      selectedResults.value = []
      draftCollection.value = null
      appliedCollection.value = null
      targetCollectionId.value = null
    }
    await loadCollections()
  }
)

// Any readable collection can be searched ...
const collectionOptions = computed(() =>
  collections.value.map(c => ({
    label: c.name ?? `Collection ${c.id}`,
    value: c.id
  }))
)

// ... but only the owner adds documents and chunks to a collection.
const targetCollectionOptions = computed(() =>
  collections.value
    .filter(c => collectionRights(c).editMembership)
    .map(c => ({ label: c.name ?? `Collection ${c.id}`, value: c.id }))
)
const canAddToCollections = computed(() => userStore.isLoggedIn && targetCollectionOptions.value.length > 0)

const collectionLabel = (id: string) => collectionOptions.value.find(option => option.value === id)?.label ?? `Collection ${id}`
const vectorLabel = (id: string) => `Embedding: ${availableVectors.value.find(v => v.id === id)?.name ?? id}`

// Recent searches (#558), kept in this browser: one history per signed-in user and one for
// signed-out use, none while a stored session is not verified yet.
const HISTORY_LIST_ID = 'search-history-list'
const historyAudience = computed<HistoryAudience | null>(() => {
  if (userStore.isLoggedIn && userStore.getUserId) return { kind: 'user', userId: String(userStore.getUserId) }
  return userStore.awaitingVerification ? null : { kind: 'anonymous' }
})
const history = useSearchHistory(searchHistoryCriteria, historyAudience, queryInput, (entry) => runFromHistory(entry))

const searchOptions = computed<SearchOptions>(() => ({
  filters: availableSearchFilters.value,
  vectors: availableVectors.value,
  collections: userStore.isLoggedIn ? collectionOptions.value.map(o => ({ id: o.value, name: o.label })) : []
}))

const historyItems = computed<SearchHistoryItem[]>(() => history.suggestions.value.map(entry => ({
  key: entryKey(entry, searchHistoryCriteria),
  query: entry.query,
  detail: describeCriteria(entry.criteria, searchOptions.value)
})))

const activeHistoryOptionId = computed(() => (
  history.shown.value && history.activeIndex.value >= 0 ? `${HISTORY_LIST_ID}-option-${history.activeIndex.value}` : undefined
))

// The input's own autofocus does not open the list; a focus that follows the user's pointer
// or key press (click, Tab) does.
let userInteracted = false
const markInteraction = () => { userInteracted = true }

function onQueryFocus () {
  if (userInteracted) history.show()
}

function onQueryKeydown (event: KeyboardEvent) {
  if (history.onKeydown(event)) return
  if (event.key === 'Enter' && !event.isComposing) {
    event.preventDefault()
    void onSearch()
  }
}

function chooseHistory (index: number) {
  const entry = history.suggestions.value[index]
  if (entry) history.choose(entry)
}

/**
 * Clears the history, but not while a search is running: that search is saved when its
 * results arrive, so it would reappear in the history just cleared.
 */
function clearHistory () {
  if (loading.value) {
    Notify.create({ message: 'A search is running. The history cannot be cleared until it finishes.', position: 'top', color: 'warning' })
    return
  }
  history.clear()
}

function removeHistory (index: number) {
  const entry = history.suggestions.value[index]
  if (entry) history.remove(entry)
}

type LoadStatus = 'loading' | 'ready' | 'failed'
const filtersStatus = ref<LoadStatus>('loading')
const vectorsStatus = ref<LoadStatus>('loading')

/**
 * Whether the lists a history entry is restored against are loaded: the offered filters,
 * the search vectors and, when signed in, the user's collections. A list that failed to
 * load makes an entry that uses it impossible to restore.
 */
function optionsStatus (criteria?: SearchHistoryCriteria): LoadStatus {
  const needed: LoadStatus[] = [filtersStatus.value]
  if (!criteria || criteria.vector) needed.push(vectorsStatus.value)
  if (!criteria || criteria.userCollectionId) {
    const userId = userStore.getUserId
    if (userStore.isLoggedIn && userId) {
      const load = collectionsLoad.value
      needed.push(load?.userId === String(userId) ? load.status : 'loading')
    }
  }
  if (needed.includes('failed')) return 'failed'
  return needed.includes('loading') ? 'loading' : 'ready'
}

const historyNote = computed(() => (optionsStatus() === 'loading' ? 'Loading search options… a search can be run from here once they are loaded.' : null))

/**
 * Runs a search from the history once the page's search options are loaded: its query and
 * criteria replace the form's; criteria no longer available are left out and named. Before
 * that nothing runs, so a pick never mixes with a later one or runs after the page is left.
 */
function runFromHistory (entry: HistoryEntry<SearchHistoryCriteria>) {
  const status = optionsStatus(entry.criteria)
  if (status === 'loading') {
    Notify.create({ message: 'Search options are still loading. Try again in a moment.', position: 'top', color: 'info' })
    return
  }
  if (status === 'failed') {
    Notify.create({
      message: 'This search cannot be restored because the search options could not be loaded. Reload the page to try again.',
      position: 'top',
      color: 'warning'
    })
    return
  }
  const restored = restoreSearch(entry.criteria, searchOptions.value)
  queryInput.value = entry.query
  draftVector.value = restored.vector
  draftCollection.value = restored.userCollectionId
  draftFilters.value = criteriaOfFilterValues('', restored.filterValues, availableSearchFilters.value)
  if (restored.dropped.length) {
    Notify.create({
      message: `Left out of this search because they are no longer available: ${restored.dropped.join(', ')}`,
      position: 'top',
      color: 'warning'
    })
  }
  void onSearch()
}

// Applied criteria as removable chips; removing one applies the search without it at once
// (and drops it from the draft, which may hold other changes not applied yet).
type AppliedChip = CriterionChip | { key: string, icon: string, label: string, without: null }

const appliedChips = computed<AppliedChip[]>(() => {
  const chips: AppliedChip[] = []
  if (appliedCollection.value) {
    chips.push({ key: 'collection', icon: 'folder', label: collectionLabel(appliedCollection.value), without: null })
  }
  if (applied.value.vector) {
    chips.push({ key: 'vector', icon: 'hub', label: vectorLabel(applied.value.vector), without: null })
  }
  return [...chips, ...criteriaChips(applied.value.criteria, availableSearchFilters.value)]
})

function removeChip (chip: AppliedChip) {
  const location: ExploreLocation = { ...applied.value }
  if (chip.key === 'collection') {
    appliedCollection.value = null
    draftCollection.value = null
  } else if (chip.key === 'vector') {
    location.vector = null
    draftVector.value = null
  } else if (chip.without) {
    location.criteria = chip.without
    const inDraft = criteriaChips(draftFilters.value, availableSearchFilters.value).find(c => c.key === chip.key)
    if (inDraft) draftFilters.value = inDraft.without
  }
  void explore.apply(location)
}

/** Clears the draft filters, collection and search vector (not the query); applied by Search. */
function clearAllFilters () {
  draftCollection.value = null
  draftVector.value = null
  draftFilters.value = emptyCriteria()
}

const draftHasFilters = computed(() => hasFilters(draftFilters.value) || draftCollection.value !== null || draftVector.value !== null)

/** Puts the applied search back into the form, discarding changes not applied. */
function discardDraft () {
  setDraft(applied.value)
  draftCollection.value = appliedCollection.value
}

function setDraft (location: ExploreLocation) {
  queryInput.value = location.criteria.textQuery ?? ''
  draftFilters.value = location.criteria
  draftVector.value = location.vector
}

// Methods

async function fetchAvailableFilters () {
  loadingFilters.value = true
  filtersStatus.value = 'loading'
  try {
    const data = await api.getAvailableSearchFiltersApiSearchFiltersGet()
    availableSearchFilters.value = data.filters || []
    filtersStatus.value = 'ready'
  } catch (e) {
    filtersStatus.value = 'failed'
    console.error('Failed to fetch available search filters:', e)
    Notify.create({ message: 'Failed to load search filters', position: 'top', color: 'warning' })
  } finally {
    loadingFilters.value = false
  }
}

async function fetchSearchVectors () {
  try {
    const data = await api.getAvailableSearchVectorsApiSearchVectorsGet()
    availableVectors.value = data.vectors
    defaultVector.value = data.defaultVector
    vectorsStatus.value = 'ready'
  } catch (e) {
    vectorsStatus.value = 'failed'
    // Without the list there is no choice to offer; searches use the server's default.
    console.error('Failed to fetch search vectors:', e)
  }
}

/** Applies the draft: a new history entry, or the same search again when nothing changed. */
async function onSearch () {
  history.close()
  const criteria = draftCriteria.value
  if (!criteria.textQuery) {
    Notify.create({ message: 'Enter a text query to search passages.', position: 'top', color: 'info' })
    return
  }
  if (criteria.textQuery.length > MAX_TEXT_QUERY_LENGTH) {
    Notify.create({ message: `The text query can be at most ${MAX_TEXT_QUERY_LENGTH.toLocaleString('en')} characters long.`, position: 'top', color: 'warning' })
    return
  }
  appliedCollection.value = draftCollection.value
  await explore.apply({ ...applied.value, criteria, vector: draftVector.value })
}

// The applied location runs once the search options are loaded: a link's values are checked
// against them first, so an unknown filter or vector is reported instead of searched.
let waitingForOptions = false

function onApplied (location: ExploreLocation, { reason, invalid }: { reason: AppliedReason, invalid: string[] }) {
  if (invalid.length) {
    Notify.create({ message: `Left out of the search because they are not valid: ${invalid.join(', ')}`, position: 'top', color: 'warning' })
  }
  if (reason === 'navigation') {
    // Back/Forward or a link: the form shows the applied search, the collection scope stays.
    setDraft(location)
    draftCollection.value = appliedCollection.value
  }
  selectedResults.value = []
  void runApplied()
}

async function runApplied () {
  if (filtersStatus.value === 'loading' || vectorsStatus.value === 'loading') {
    waitingForOptions = true
    return
  }
  waitingForOptions = false
  const location = applied.value
  const dropped: string[] = []
  const corrected: ExploreLocation = { ...location }
  if (filtersStatus.value === 'ready') {
    const offered = offeredCriteria(location.criteria, availableSearchFilters.value)
    dropped.push(...offered.dropped)
    corrected.criteria = offered.criteria
  }
  if (location.vector && vectorsStatus.value === 'ready' && !availableVectors.value.some(v => v.id === location.vector)) {
    dropped.push(vectorLabel(location.vector))
    corrected.vector = null
  }
  // Only Passages results exist so far (#605); Documents and Visualizations follow (#527b/c, #528).
  if (location.mode === 'documents') dropped.push('Documents results (not available yet; showing passages)')
  if (location.view === 'visualizations') dropped.push('Visualizations (not available yet)')
  if (location.mode === 'documents') corrected.mode = null
  if (location.view === 'visualizations') corrected.view = null
  if (dropped.length) {
    Notify.create({ message: `Left out of the search because they are not available: ${dropped.join(', ')}`, position: 'top', color: 'warning' })
    setDraft(corrected)
    await explore.apply(corrected, { replace: true }) // runs the corrected search
    return
  }

  if (!location.criteria.textQuery) {
    passages.cancel()
    return
  }
  const query = { criteria: location.criteria, vector: location.vector, userCollectionId: appliedCollection.value }
  const found = await passages.search(query)
  if (!found) return // failed (shown) or replaced by a newer search
  // Only a search that ran is remembered (with no results too); a failed one is not.
  const recorded = history.record(location.criteria.textQuery, criteriaOfRequest({
    query: location.criteria.textQuery,
    type: SearchType.hybrid,
    vector: location.vector,
    userCollectionId: query.userCollectionId,
    filters: historyFiltersOf(location.criteria, availableSearchFilters.value),
    tagUuids: [],
    positive: false,
    automatic: false
  }))
  if (recorded === 'tooLong') {
    Notify.create({
      message: `Not added to recent searches: the query is longer than ${MAX_QUERY_LENGTH.toLocaleString('en')} characters.`,
      position: 'top',
      color: 'info'
    })
  }
}

watch([filtersStatus, vectorsStatus], () => {
  if (waitingForOptions) void runApplied()
})

async function addSelectedChunksToCollection () {
  if (!targetCollectionId.value) {
    Notify.create({ message: 'Please select a collection first.', position: 'top', color: 'warning' })
    return
  }
  if (selectedResults.value.length === 0) {
    Notify.create({ message: 'No chunks selected.', position: 'top', color: 'warning' })
    return
  }

  // Signing out (or another account) stops the remaining adds; completed ones are kept,
  // and the old session's outcome is no longer reported.
  const inSession = captureSession()
  const collectionId = targetCollectionId.value
  let successCount = 0
  let failedCount = 0
  for (const chunkId of [...selectedResults.value]) {
    if (!inSession()) return
    try {
      const data = await api.addChunkToCollectionApiUserCollectionsCollectionIdChunksChunkIdPost({ collectionId, chunkId })
      // Partial: the chunk may be linked while its document link failed.
      if (data.outcome === WriteOutcome.complete) successCount++
      else failedCount++
    } catch (e) {
      failedCount++
      console.error(e)
    }
  }
  if (!inSession()) return
  Notify.create({ message: `Added ${successCount} chunk(s) to collection`, position: 'top', color: 'positive' })
  if (failedCount) {
    Notify.create({ message: `${failedCount} chunk(s) could not be fully added; completed links were kept.`, position: 'top', color: 'negative' })
  }
}

async function addSelectedDocumentsToCollection () {
  if (!targetCollectionId.value) {
    Notify.create({ message: 'Please select a collection first.', position: 'top', color: 'warning' })
    return
  }
  if (selectedResults.value.length === 0) {
    Notify.create({ message: 'No chunks selected.', position: 'top', color: 'warning' })
    return
  }

  let successCount = 0
  const docIds = new Set(
    results.value
      .filter(r => selectedResults.value.includes(r.id))
      .map(r => r.documentObject.id)
      .filter(id => id !== undefined)
  )

  const inSession = captureSession()
  const collectionId = targetCollectionId.value
  for (const documentId of docIds) {
    if (!inSession()) return // signed out meanwhile: stop, keep what was added
    // The store reports failures itself and returns true only for a complete add.
    if (await documentsStore.addToCollection(documentId, collectionId)) successCount++
  }
  if (!inSession()) return
  Notify.create({ message: `Added ${successCount} document(s) to collection`, position: 'top', color: 'positive' })
}

// The applied location: the URL now, and on every Back/Forward or link (applies at once).
const explore = useExploreLocation('search', (location, details) => {
  applied.value = location
  onApplied(location, details)
})

// Kept alive while a document opened from a result is shown: the listeners only while shown.
whileShown(() => {
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('pointerdown', markInteraction, { capture: true })
  window.addEventListener('keydown', markInteraction, { capture: true })
}, () => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('pointerdown', markInteraction, { capture: true })
  window.removeEventListener('keydown', markInteraction, { capture: true })
})

onMounted(async () => {
  await Promise.all([fetchAvailableFilters(), fetchSearchVectors()])
  await loadCollections()
})

onBeforeUnmount(() => {
  passages.cancel()
  if (clearHighlightTimer !== null) {
    window.clearTimeout(clearHighlightTimer)
  }
})

</script>

<style scoped>
.selection-toolbar__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  margin-top: 4px;
}

.selection-toolbar__collection {
  flex: 1 1 220px;
}

.results-status {
  min-height: 160px;
  text-align: center;
}

:deep(.active-filter-chip .q-chip__icon--remove) {
  margin-left: 5px;
}
</style>
