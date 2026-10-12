<template>
  <q-page :class="results.length ? 'q-pa-md bg-grey-1' : 'q-pa-md bg-grey-1 flex flex-center'">
    <div style="width: 100%; max-width: 1400px; margin: 0 auto;">

      <q-card flat bordered class="q-mb-xl bg-white">
        <q-form @submit.prevent="onSearch">
          <q-card-section>
            <div class="row q-col-gutter-sm items-center">
              <div class="col">
                <q-input
                  v-model="searchForm.query"
                  dense
                  outlined
                  required
                  autofocus
                  @keydown.enter.prevent="onSearch"
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
              </div>

              <div class="col-auto">
                <q-btn
                  flat
                  color="primary"
                  icon="tune"
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

    <RightSidebarPanel v-if="results.length || loading" id="search-summary" label="Summary" icon="auto_awesome">
      <SearchSummaryPanel
        :tokens="searchSummary.tokens"
        :time-spent="searchSummary.timeSpent"
        v-model:brevity="searchSummary.brevity"
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
import { ref, computed, onMounted, nextTick, onBeforeUnmount, reactive, watch } from 'vue'
import { QPage, QForm, QInput, QBtn, QCard, QCardSection, QSeparator, QSelect, QRange, QPagination, Notify, useQuasar } from 'quasar'
import { SearchType, WriteOutcome, type SearchFilter, type SearchFilterInput, type SearchRequest, type SearchResultChunk } from 'src/generated/api'
import { useApi } from 'src/shared/api'
import { useUserStore } from 'src/stores/user-store'
import useCollections from 'src/composables/useCollections'
import useDocuments from 'src/composables/useDocuments'
import { collectionRights } from 'src/features/collections/permissions'
import { useSearchRequest } from 'src/features/search/useSearchRequest'
import { useSearchSummary } from 'src/features/search/useSearchSummary'
import SearchSummaryPanel from 'src/features/search/SearchSummaryPanel.vue'
import SearchResultCard from 'src/features/search/SearchResultCard.vue'
import { escapeClearsSelection } from 'src/features/search/resultLayout'
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
  automatic: true
})

// Dynamic Filter Data State
type IntervalValue = { min: number, max: number }
const loadingFilters = ref(false)
const availableSearchFilters = ref<SearchFilter[]>([])
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const filterValues = ref<Record<string, any>>({})

function formatFilterLabel (id: string): string {
  return id
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

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

/** Range of an interval filter (the generated client types its numeric bounds loosely). */
function intervalBounds (filter: SearchFilter): IntervalValue {
  const min = filter.minValue != null ? Math.floor(Number(filter.minValue)) : 1800
  const max = filter.maxValue != null ? Math.ceil(Number(filter.maxValue)) : 2026
  return { min, max }
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
const { collections, loading: collectionsLoading, loadCollections: fetchCollections } = useCollections()
const apiDocumentClient = useDocuments()

async function loadCollections () {
  if (!userStore.isLoggedIn) return
  await fetchCollections()
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

type ActiveFilterBadge = {
  key: string
  type: 'collection' | 'dynamic'
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
        const nominalObj = filter.values?.find(v => v.backendForm === selectedBackendVal || v.userForm === selectedBackendVal)
        const displayLabel = nominalObj ? nominalObj.userForm : selectedBackendVal
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
  } catch (e) {
    console.error('Failed to fetch available search filters:', e)
    Notify.create({ message: 'Failed to load search filters', position: 'top', color: 'warning' })
  } finally {
    loadingFilters.value = false
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

  try {
    const context = await searchRequest.search(request)
    if (!context) return // replaced by a newer search
    if (context.response.results.length === 0) {
      Notify.create({ message: 'No results found', position: 'top', color: 'info' })
    }
    for (const warning of context.response.warnings ?? []) {
      Notify.create({ message: warning, position: 'top', color: 'warning' })
    }
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

  let successCount = 0
  let failedCount = 0
  for (const chunkId of selectedResults.value) {
    try {
      const data = await api.addChunkToCollectionApiUserCollectionsCollectionIdChunksChunkIdPost({ collectionId: targetCollectionId.value as string, chunkId })
      // Partial: the chunk may be linked while its document link failed.
      if (data.outcome === WriteOutcome.complete) successCount++
      else failedCount++
    } catch (e) {
      failedCount++
      console.error(e)
    }
  }
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

  for (const documentId of docIds) {
    // The store reports failures itself and returns true only for a complete add.
    if (await apiDocumentClient.addDocToCollection(documentId, targetCollectionId.value)) successCount++
  }
  Notify.create({ message: `Added ${successCount} document(s) to collection`, position: 'top', color: 'positive' })
}

onMounted(async () => {
  window.addEventListener('keydown', onKeydown)
  await fetchAvailableFilters()
  await loadCollections()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
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
