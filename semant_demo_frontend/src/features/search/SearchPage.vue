<template>
  <q-page :class="results.length ? 'q-pa-md bg-grey-1' : 'q-pa-md bg-grey-1 flex flex-center'">
    <div style="width: 100%; max-width: 1400px; margin: 0 auto;">

      <q-card flat bordered class="q-mb-xl bg-white">
        <q-form @submit.prevent="onSearch">
          <q-card-section>
            <div class="row q-col-gutter-sm items-center">
              <div class="col relative-position">
                <!-- Recent searches (#558) open under the input when it is focused by the user,
                     clicked or typed into; not on the page's own autofocus. -->
                <q-input
                  v-model="searchForm.query"
                  dense
                  outlined
                  required
                  autofocus
                  autocomplete="off"
                  aria-label="Search query"
                  role="combobox"
                  aria-autocomplete="list"
                  :aria-expanded="history.shown.value"
                  :aria-controls="history.shown.value ? HISTORY_LIST_ID : undefined"
                  :aria-activedescendant="activeHistoryOptionId"
                  data-testid="search-query"
                  @keydown="onQueryKeydown"
                  @focus="onQueryFocus"
                  @click="history.show"
                  @blur="history.close"
                  @update:model-value="history.show"
                >
                  <template v-slot:prepend>
                    <q-btn
                      type="submit"
                      color="primary"
                      icon="search"
                      round
                      flat
                      dense
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

            <div v-if="activeFilterBadges.length" class="row q-gutter-sm q-mt-sm">
              <q-chip
                v-for="badge in activeFilterBadges"
                :key="badge.key"
                removable
                color="primary"
                text-color="white"
                class="active-filter-chip"
                @remove="removeFilterBadge(badge)"
              >
                <q-icon :name="badge.icon" size="16px" class="q-mr-xs" />
                {{ badge.label }}
              </q-chip>
            </div>
          </q-card-section>

          <q-slide-transition>
            <div v-show="showFilters">
              <div class="relative-position q-pt-sm">
                <q-separator inset />
                <div class="absolute bg-white q-px-sm" style="z-index: 1; bottom: 0; left: 50%; transform: translate(-50%, 50%);" v-if="activeFilterBadges.length">
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
              <q-card-section class="bg-grey-1" :style="activeFilterBadges.length ? 'padding-top: 24px;' : ''">
                <div class="row q-col-gutter-md">

                  <div v-if="userStore.isLoggedIn" class="col-12 col-sm-6 col-md-4">
                    <q-select
                      v-model="searchForm.userCollectionId"
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
                      v-for="filter in availableSearchFilters"
                      :key="filter.id"
                      class="col-12 col-sm-6 col-md-4"
                    >
                      <!-- Interval Filter -->
                      <div v-if="filter.type === 'interval'">
                        <div class="row items-center text-subtitle2 q-mb-xs text-grey-8">
                          <q-icon :name="getFilterIcon(filter.id)" size="18px" class="q-mr-xs" />
                          <span>{{ formatFilterLabel(filter.id) }}: {{ filterValues[filter.id]?.min }} - {{ filterValues[filter.id]?.max }}</span>
                        </div>
                        <div class="q-px-sm" v-if="filterValues[filter.id]">
                          <q-range
                            v-model="filterValues[filter.id]"
                            :min="intervalBounds(filter).min"
                            :max="intervalBounds(filter).max"
                            :step="1"
                            label
                            color="primary"
                          />
                        </div>
                      </div>

                      <!-- Nominal Filter -->
                      <div v-else-if="filter.type === 'nominal' && filter.values">
                        <q-select
                          v-model="filterValues[filter.id]"
                          :options="getNominalOptions(filter)"
                          :label="formatFilterLabel(filter.id)"
                          multiple
                          use-chips
                          outlined
                          dense
                          emit-value
                          map-options
                          clearable
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

      <div v-if="results.length">
        <div class="row items-end justify-between q-mb-md">
          <div>
            <div class="text-h5 text-weight-medium">Results ({{ results.length }})</div>
            <div class="text-caption text-grey-7">Search completed in {{ timeSpent.toFixed(2) }}s</div>
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
            v-for="(chunk, index) in paginatedResults"
            :id="`result-${resultNumber(index)}`"
            :key="chunk.id"
            :chunk="chunk"
            :number="resultNumber(index)"
            :filters="availableSearchFilters"
            :selected="selectedResults.includes(chunk.id)"
            :highlighted="highlightedDocNumber === resultNumber(index)"
            :context-shown="contextResultNumber === resultNumber(index)"
            @update:selected="setSelected(chunk.id, $event)"
            @view-context="viewContext(chunk, resultNumber(index))"
          />
        </div>

        <div class="flex flex-center q-mt-xl">
          <q-pagination
            v-model="currentPage"
            :max="totalPages"
            :max-pages="7"
            boundary-numbers
            direction-links
            color="primary"
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
import { ref, computed, onMounted, nextTick, onBeforeUnmount, reactive, watch } from 'vue'
import { QPage, QForm, QInput, QBtn, QCard, QCardSection, QSeparator, QSelect, QRange, QPagination, QItem, QItemSection, QItemLabel, Notify, useQuasar } from 'quasar'
import { SearchType, WriteOutcome, type SearchFilter, type SearchFilterInput, type SearchRequest, type SearchResultChunk, type SearchVectorInfo } from 'src/generated/api'
import { captureSession, reportAiOperation, useApi } from 'src/shared/api'
import { generatesText, searchQuotaMessage } from './searchQuota'
import { useUserStore } from 'src/features/auth/userStore'
import { useUserCollectionsStore } from 'src/features/user_collections/userCollectionsStore'
import { useDocumentsStore } from 'src/features/documents/documentsStore'
import { collectionRights } from 'src/features/user_collections/permissions'
import { useSearchRequest } from './useSearchRequest'
import { useSearchSummary } from './useSearchSummary'
import SearchSummaryPanel from './SearchSummaryPanel.vue'
import SearchResultCard from './SearchResultCard.vue'
import { escapeClearsSelection } from './resultLayout'
import { formatFilterLabel, intervalBounds, nominalLabel } from './searchFilters'
import { criteriaOfRequest, describeCriteria, restoreSearch, searchHistoryCriteria, type SearchHistoryCriteria, type SearchOptions } from './searchHistoryCriteria'
import SearchHistoryDropdown from 'src/shared/searchHistory/SearchHistoryDropdown.vue'
import { useSearchHistory } from 'src/shared/searchHistory/useSearchHistory'
import { entryKey, MAX_QUERY_LENGTH, type HistoryAudience, type HistoryEntry, type SearchHistoryItem } from 'src/shared/searchHistory/history'
import RightSidebarPanel from 'src/app/sidebar/RightSidebarPanel.vue'
import { useRightSidebarStore } from 'src/app/sidebar/rightSidebarStore'
import ChunkContextPanel from 'src/features/documents/ChunkContextPanel.vue'
import { useChunkContext } from 'src/features/documents/useChunkContext'

const api = useApi().default

// Search Form State
const showFilters = ref(false)
const searchForm = ref<SearchRequest>({
  query: '',
  limit: 50, // Increased default to show pagination better
  userCollectionId: null,
  type: SearchType.hybrid,
  searchTitleGenerate: false,
  searchSummaryGenerate: false,
  searchResultsSummaryGenerate: false,
  filters: null,
  minYear: null,
  maxYear: null,
  minDate: null,
  maxDate: null,
  language: null,
  tagUuids: [],
  positive: true,
  automatic: true,
  vector: null // the configured default
})

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
  get: () => searchForm.value.vector ?? defaultVector.value,
  set: (id) => { searchForm.value.vector = id === defaultVector.value ? null : id }
})

// Dynamic Filter Data State
const loadingFilters = ref(false)
const availableSearchFilters = ref<SearchFilter[]>([])
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const filterValues = ref<Record<string, any>>({})

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

// Results State: the current search context (results as retrieved)
const searchRequest = useSearchRequest()
const loading = searchRequest.loading
const results = computed<SearchResultChunk[]>(() => searchRequest.context.value?.response.results ?? [])
const timeSpent = computed(() => searchRequest.context.value?.response.timeSpent ?? 0)
const selectedResults = ref<string[]>([])
const targetCollectionId = ref<string | null>(null)

// Pagination State
const currentPage = ref(1)
const itemsPerPage = ref(10)
const totalPages = computed(() => Math.ceil(results.value.length / itemsPerPage.value))
const paginatedResults = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage.value
  return results.value.slice(start, start + itemsPerPage.value)
})

/** 1-based position in the whole result list of the `index`-th result on this page. */
function resultNumber (index: number): number {
  return (currentPage.value - 1) * itemsPerPage.value + index + 1
}

function clearSelection () {
  selectedResults.value = []
}

// Escape clears the whole selection (all pages) unless a field or overlay needs it.
function onKeydown (event: KeyboardEvent) {
  if (selectedResults.value.length && escapeClearsSelection(event)) clearSelection()
}

function setSelected (chunkId: string, selected: boolean) {
  const others = selectedResults.value.filter(id => id !== chunkId)
  selectedResults.value = selected ? [...others, chunkId] : others
}

// Summarization (right sidebar): works on the current results or the selected ones
const searchSummary = reactive(useSearchSummary(searchRequest.context, selectedResults))

// Citations
const highlightedDocNumber = ref<number | null>(null)
let clearHighlightTimer: number | null = null

async function jumpToResult (docNumber: number) {
  const resultIndex = docNumber - 1
  if (resultIndex < 0 || resultIndex >= results.value.length) {
    Notify.create({ message: `Result [${docNumber}] is not available.`, position: 'top', color: 'warning' })
    return
  }

  currentPage.value = Math.floor(resultIndex / itemsPerPage.value) + 1
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

async function viewContext (chunk: SearchResultChunk, number: number) {
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
// panel, so the view never shows a result that is no longer in the list.
watch(() => searchRequest.context.value?.id, () => {
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
      searchRequest.cancel()
      selectedResults.value = []
      searchForm.value.userCollectionId = null
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

// Recent searches (#558), kept in this browser: one history per signed-in user and one for
// signed-out use, none while a stored session is not verified yet.
const HISTORY_LIST_ID = 'search-history-list'
const historyAudience = computed<HistoryAudience | null>(() => {
  if (userStore.isLoggedIn && userStore.getUserId) return { kind: 'user', userId: String(userStore.getUserId) }
  return userStore.awaitingVerification ? null : { kind: 'anonymous' }
})
const queryText = computed(() => searchForm.value.query ?? '')
const history = useSearchHistory(searchHistoryCriteria, historyAudience, queryText, (entry) => runFromHistory(entry))

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
  if (!criteria || criteria.collectionId) {
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
 * criteria replace the form's (generated titles and summaries stay as currently chosen);
 * criteria no longer available are left out and named. Before that nothing runs, so a pick
 * never mixes with a later one or runs after the page is left.
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
  searchForm.value.query = entry.query
  searchForm.value.type = restored.type
  searchForm.value.vector = restored.vector
  searchForm.value.userCollectionId = restored.collectionId
  filterValues.value = restored.filterValues
  if (restored.dropped.length) {
    Notify.create({
      message: `Left out of this search because they are no longer available: ${restored.dropped.join(', ')}`,
      position: 'top',
      color: 'warning'
    })
  }
  void onSearch()
}

type ActiveFilterBadge = {
  key: string
  type: 'collection' | 'vector' | 'dynamic'
  filterId?: string
  icon: string
  label: string
  value?: string
}

const selectedCollectionLabel = computed(() => {
  if (!searchForm.value.userCollectionId) return null
  const option = collectionOptions.value.find(option => option.value === searchForm.value.userCollectionId)
  return option?.label ?? `Collection ${searchForm.value.userCollectionId}`
})

const activeFilterBadges = computed<ActiveFilterBadge[]>(() => {
  const badges: ActiveFilterBadge[] = []

  if (searchForm.value.userCollectionId) {
    badges.push({
      key: `collection:${searchForm.value.userCollectionId}`,
      type: 'collection',
      icon: 'folder',
      label: selectedCollectionLabel.value ?? searchForm.value.userCollectionId
    })
  }

  if (searchForm.value.vector) {
    const id = searchForm.value.vector
    badges.push({
      key: `vector:${id}`,
      type: 'vector',
      icon: 'hub',
      label: `Embedding: ${availableVectors.value.find(v => v.id === id)?.name ?? id}`
    })
  }

  availableSearchFilters.value.forEach(filter => {
    const val = filterValues.value[filter.id]
    if (!val) return

    if (filter.type === 'interval') {
      const bounds = intervalBounds(filter)
      if (val.min !== bounds.min || val.max !== bounds.max) {
        badges.push({
          key: `interval:${filter.id}`,
          type: 'dynamic',
          filterId: filter.id,
          icon: getFilterIcon(filter.id),
          label: `${formatFilterLabel(filter.id)}: ${val.min}-${val.max}`
        })
      }
    } else if (filter.type === 'nominal' && Array.isArray(val) && val.length > 0) {
      val.forEach((selectedBackendVal: string) => {
        const displayLabel = nominalLabel(filter, selectedBackendVal)
        badges.push({
          key: `nominal:${filter.id}:${selectedBackendVal}`,
          type: 'dynamic',
          filterId: filter.id,
          icon: getFilterIcon(filter.id),
          label: `${formatFilterLabel(filter.id)}: ${displayLabel}`,
          value: selectedBackendVal
        })
      })
    }
  })

  return badges
})

function removeFilterBadge (badge: ActiveFilterBadge) {
  if (badge.type === 'collection') {
    searchForm.value.userCollectionId = null
    return
  }
  if (badge.type === 'vector') {
    searchForm.value.vector = null
    return
  }

  if (badge.filterId && filterValues.value[badge.filterId]) {
    const filter = availableSearchFilters.value.find(f => f.id === badge.filterId)
    if (!filter) return

    if (filter.type === 'interval') {
      filterValues.value[badge.filterId] = intervalBounds(filter)
    } else if (filter.type === 'nominal' && badge.value) {
      const current = filterValues.value[badge.filterId] as string[]
      filterValues.value[badge.filterId] = current.filter(v => v !== badge.value)
    }
  }
}

function clearAllFilters () {
  searchForm.value.userCollectionId = null
  searchForm.value.vector = null
  availableSearchFilters.value.forEach(filter => {
    if (filter.type === 'interval') {
      filterValues.value[filter.id] = intervalBounds(filter)
    } else if (filter.type === 'nominal') {
      filterValues.value[filter.id] = []
    }
  })
}

// Methods

async function fetchAvailableFilters () {
  loadingFilters.value = true
  filtersStatus.value = 'loading'
  try {
    const data = await api.getAvailableSearchFiltersApiSearchFiltersGet()
    availableSearchFilters.value = data.filters || []

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const valuesMap: Record<string, any> = {}
    availableSearchFilters.value.forEach(filter => {
      if (filter.type === 'interval') {
        valuesMap[filter.id] = intervalBounds(filter)
      } else if (filter.type === 'nominal') {
        valuesMap[filter.id] = []
      }
    })
    filterValues.value = valuesMap
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

async function onSearch () {
  selectedResults.value = []
  currentPage.value = 1 // reset pagination

  // Build dynamic filters payload
  const filtersPayload: SearchFilterInput[] = []

  availableSearchFilters.value.forEach(filter => {
    const val = filterValues.value[filter.id]
    if (!val) return

    if (filter.type === 'interval') {
      const bounds = intervalBounds(filter)
      if (val.min !== bounds.min || val.max !== bounds.max) {
        filtersPayload.push({
          id: filter.id,
          minValue: val.min,
          maxValue: val.max
        })
      }
    } else if (filter.type === 'nominal' && Array.isArray(val) && val.length > 0) {
      filtersPayload.push({
        id: filter.id,
        values: val
      })
    }
  })

  // Attach filters array to request, clearing legacy fields
  const request: SearchRequest = {
    ...searchForm.value,
    filters: filtersPayload.length > 0 ? filtersPayload : null,
    minYear: null,
    maxYear: null,
    language: null
  }
  history.close()

  try {
    const context = await searchRequest.search(request)
    if (!context) return // replaced by a newer search
    // Only a search that ran is remembered (with no results too); a failed one is not.
    if (history.record(request.query, criteriaOfRequest(request)) === 'tooLong') {
      Notify.create({
        message: `Not added to recent searches: the query is longer than ${MAX_QUERY_LENGTH.toLocaleString('en')} characters.`,
        position: 'top',
        color: 'info'
      })
    }
    if (context.response.results.length === 0) {
      Notify.create({ message: 'No results found', position: 'top', color: 'info' })
    }
    // Generated titles/summaries skipped for the daily AI allowance: the results stand; the
    // backend's warning is replaced by the allowance message (local reset time), shown as
    // information rather than as a provider failure.
    const refusal = context.response.quotaExhausted
    for (const warning of context.response.warnings ?? []) {
      if (refusal && warning.includes(refusal.detail)) continue
      Notify.create({ message: warning, position: 'top', color: 'warning' })
    }
    if (refusal) {
      Notify.create({ message: searchQuotaMessage(refusal), position: 'top', color: 'info', icon: 'hourglass_bottom' })
    }
    if (refusal || generatesText(request)) reportAiOperation()
  } catch (e) {
    console.error(e)
    Notify.create({ message: 'Search failed', position: 'top', color: 'negative' })
  }
}

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

onMounted(async () => {
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('pointerdown', markInteraction, { capture: true })
  window.addEventListener('keydown', markInteraction, { capture: true })
  await Promise.all([fetchAvailableFilters(), fetchSearchVectors()])
  await loadCollections()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('pointerdown', markInteraction, { capture: true })
  window.removeEventListener('keydown', markInteraction, { capture: true })
  searchRequest.cancel()
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

:deep(.active-filter-chip .q-chip__icon--remove) {
  margin-left: 5px;
}
</style>
