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
          <div v-show="userStore.isLoggedIn && selectedResults.length > 0" class="q-mb-lg">
            <q-card flat bordered class="bg-primary text-white">
              <q-card-section class="row items-center justify-between q-pa-sm">
                <div class="text-subtitle2 q-ml-sm">{{ selectedResults.length }} item(s) selected</div>
                <div class="row q-gutter-sm items-center">
                  <q-select
                    v-model="targetCollectionId"
                    :options="targetCollectionOptions"
                    label="Select Collection"
                    dense
                    outlined
                    dark
                    emit-value
                    map-options
                    style="min-width: 220px"
                  />
                  <q-btn flat color="white" icon="library_add" label="Add Chunks" @click="addSelectedChunksToCollection" />
                  <q-btn flat color="white" icon="post_add" label="Add Documents" @click="addSelectedDocumentsToCollection" />
                  <q-btn flat color="white" icon="close" round dense @click="selectedResults = []" />
                </div>
              </q-card-section>
            </q-card>
          </div>
        </q-slide-transition>

        <div class="q-gutter-y-md">
          <q-card
            v-for="(chunk, index) in paginatedResults"
            :id="`result-${(currentPage - 1) * itemsPerPage + index + 1}`"
            :key="chunk.id"
            flat
            bordered
            class="bg-white"
            :class="{ 'citation-target-highlight': highlightedDocNumber === (currentPage - 1) * itemsPerPage + index + 1 }"
          >
            <q-card-section class="row no-wrap items-start">
              <div class="col">
                <div class="text-h6 text-primary" style="line-height: 1.2;">
                  {{ (currentPage - 1) * itemsPerPage + index + 1 }}. {{ chunk.queryTitle || chunk.title || "N/A" }}
                </div>
                <div class="row q-gutter-x-md text-caption text-grey-8 q-mt-xs">
                  <div><q-icon name="person" class="q-mr-xs"/>{{ chunk.documentObject.author?.join(', ') || 'Unknown Author' }}</div>
                  <div><q-icon name="event" class="q-mr-xs"/>{{ chunk.documentObject.yearIssued || 'Year N/A' }}</div>
                  <div><q-icon name="language" class="q-mr-xs"/>{{ chunk.language || 'N/A' }}</div>
                  <div><q-icon name="description" class="q-mr-xs"/>Pages: {{ chunk.fromPage }}–{{ chunk.toPage }}</div>
                </div>
                <div class="text-caption text-grey-8 q-mt-xs" v-if="chunk.documentObject.title">
                  <strong>Source:</strong> {{ chunk.documentObject.title }}
                </div>
              </div>
              <div class="q-mr-md q-mt-xs">
                <q-checkbox v-model="selectedResults" :val="chunk.id" color="primary" dense />
              </div>
            </q-card-section>

            <q-separator inset />

            <q-card-section>
              <div class="text-body1" style="white-space: pre-wrap; color: #333;">
                {{ chunk.text }}
              </div>

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
  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, onBeforeUnmount, reactive, watch } from 'vue'
import { QPage, QForm, QInput, QBtn, QCard, QCardSection, QSeparator, QSelect, QCheckbox, QRange, QPagination, Notify } from 'quasar'
import { SearchType, WriteOutcome, type SearchFilter, type SearchFilterInput, type SearchRequest, type TextChunkWithDocument } from 'src/generated/api'
import { useApi } from 'src/shared/api'
import { useUserStore } from 'src/stores/user-store'
import useCollections from 'src/composables/useCollections'
import useDocuments from 'src/composables/useDocuments'
import { collectionRights } from 'src/features/collections/permissions'
import { useSearchRequest } from 'src/features/search/useSearchRequest'
import { useSearchSummary } from 'src/features/search/useSearchSummary'
import SearchSummaryPanel from 'src/features/search/SearchSummaryPanel.vue'
import RightSidebarPanel from 'src/app/sidebar/RightSidebarPanel.vue'

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
const results = computed<TextChunkWithDocument[]>(() => searchRequest.context.value?.response.results ?? [])
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
      const data = await api.addChunkToCollectionApiUserCollectionCollectionIdChunksChunkIdPost({ collectionId: targetCollectionId.value as string, chunkId })
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
  await fetchAvailableFilters()
  await loadCollections()
})

onBeforeUnmount(() => {
  searchRequest.cancel()
  if (clearHighlightTimer !== null) {
    window.clearTimeout(clearHighlightTimer)
  }
})

</script>

<style scoped>
.citation-target-highlight {
  outline: 2px solid var(--q-secondary) !important;
  outline-offset: 0;
}

:deep(.active-filter-chip .q-chip__icon--remove) {
  margin-left: 5px;
}
</style>
