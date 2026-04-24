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
              <q-separator inset />
              <q-card-section class="bg-grey-1">
                <div class="row q-col-gutter-xl">

                  <div v-if="userStore.isLoggedIn" class="col-12 col-md-4">
                    <q-select
                      v-model="searchForm.user_collection_id"
                      :options="collectionOptions"
                      label="Select a Collection"
                      outlined
                      dense
                      emit-value
                      map-options
                      clearable
                      :loading="loading"
                    >
                      <template v-slot:prepend>
                        <q-icon name="folder" />
                      </template>
                    </q-select>
                  </div>

                  <div class="col-12 col-md-4">
                    <div class="row items-center text-subtitle2 q-mb-sm text-grey-8">
                      <q-icon name="language" size="18px" class="q-mr-xs" />
                      <span>Languages</span>
                    </div>
                    <div v-if="loadingFilters" class="text-caption text-grey">Loading languages...</div>
                    <div class="row q-gutter-x-md" v-else>
                      <q-checkbox
                        v-for="lang in availableLanguages"
                        :key="lang"
                        v-model="selectedLanguages"
                        :val="lang"
                        :label="lang"
                        dense
                        color="primary"
                      />
                    </div>
                  </div>

                  <div class="col-12 col-md-4">
                    <div class="row items-center text-subtitle2 q-mb-sm text-grey-8">
                      <q-icon name="event" size="18px" class="q-mr-xs" />
                      <span>Year Range: {{ yearRange.min }} - {{ yearRange.max }}</span>
                    </div>
                    <div v-if="loadingFilters" class="text-caption text-grey">Loading years...</div>
                    <div class="q-px-md" v-else>
                      <q-range
                        v-model="yearRange"
                        :min="availableYears.min"
                        :max="availableYears.max"
                        :step="1"
                        label
                        color="primary"
                        @update:model-value="updateYearFilters"
                      />
                    </div>
                  </div>

                </div>
              </q-card-section>
            </div>
          </q-slide-transition>

        </q-form>
      </q-card>

      <div v-if="results.length" class="q-mb-xl">
        <div class="row q-col-gutter-md">
          <div class="col-12">
            <q-card flat bordered class="bg-white">
              <q-card-section class="row items-center justify-between q-col-gutter-sm">
                <div class="text-subtitle2 text-grey-8">Summarization</div>
                <div class="row q-gutter-sm">
                  <q-btn
                    color="secondary"
                    icon="auto_awesome"
                    label="Summarize Results"
                    :loading="summarizing"
                    @click="onSummarize"
                    class="q-px-md"
                  />
                  <q-btn
                    flat
                    color="secondary"
                    icon="tune"
                    @click="showSummarizeOptions = !showSummarizeOptions"
                  />
                </div>
              </q-card-section>

              <q-slide-transition>
                <div v-show="showSummarizeOptions">
                  <q-separator inset />
                  <q-card-section class="bg-grey-1">
                    <div class="row q-col-gutter-md items-center">
                      <div class="col-12 col-md row no-wrap q-gutter-md items-center">
                        <q-select
                          v-model="brevityType"
                          :options="brevityTypes"
                          label="Brevity"
                          dense
                          outlined
                          class="col"
                          emit-value
                          map-options
                        />
                        <q-select
                          v-model="summaryScope"
                          :options="scopeOptions"
                          label="Scope"
                          dense
                          outlined
                          class="col"
                          emit-value
                          map-options
                        />
                      </div>
                    </div>
                  </q-card-section>
                </div>
              </q-slide-transition>

              <q-separator />
              <q-card-section class="bg-blue-grey-1" v-if="summary">
                <div class="text-caption text-grey q-mb-sm">Time spent: {{ summaryTimeSpent.toFixed(2) }}s</div>
                <div class="text-body2" style="white-space: pre-wrap;">
                  <template v-for="(token, idx) in parsedSummaryTokens" :key="idx">
                    <span v-if="token.type === 'text'">{{ token.value }}</span>
                    <span v-else>
                      <a
                          href="#"
                          class="citation-link"
                          @click.prevent="jumpToResult(token.docNumber)"
                        >[{{ token.docNumber }}]</a>
                    </span>
                  </template>
                </div>
              </q-card-section>
            </q-card>
          </div>
        </div>
      </div>

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
                    :options="collectionOptions"
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
                  {{ (currentPage - 1) * itemsPerPage + index + 1 }}. {{ chunk.query_title || chunk.title || "N/A" }}
                </div>
                <div class="row q-gutter-x-md text-caption text-grey-8 q-mt-xs">
                  <div><q-icon name="person" class="q-mr-xs"/>{{ chunk.document_object.author || 'Unknown Author' }}</div>
                  <div><q-icon name="event" class="q-mr-xs"/>{{ chunk.document_object.yearIssued || 'Year N/A' }}</div>
                  <div><q-icon name="language" class="q-mr-xs"/>{{ chunk.language || 'N/A' }}</div>
                  <div><q-icon name="description" class="q-mr-xs"/>Pages: {{ chunk.from_page }}–{{ chunk.to_page }}</div>
                </div>
                <div class="text-caption text-grey-8 q-mt-xs" v-if="chunk.document_object.title">
                  <strong>Source:</strong> {{ chunk.document_object.title }}
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

              <div class="q-mt-md" v-if="chunk.ner_P?.length || chunk.ner_G?.length || chunk.ner_I?.length || chunk.ner_M?.length || chunk.ner_O?.length">
                <div class="text-subtitle2 text-grey-7 q-mb-xs">Named Entities</div>
                <div class="row q-gutter-sm">
                  <q-badge color="blue-1" text-color="blue-9" class="q-pa-sm" v-if="chunk.ner_P?.length">
                    <strong>People:</strong>&nbsp;{{ chunk.ner_P.join(', ') }}
                  </q-badge>
                  <q-badge color="green-1" text-color="green-9" class="q-pa-sm" v-if="chunk.ner_G?.length">
                    <strong>Places:</strong>&nbsp;{{ chunk.ner_G.join(', ') }}
                  </q-badge>
                  <q-badge color="purple-1" text-color="purple-9" class="q-pa-sm" v-if="chunk.ner_I?.length">
                    <strong>Institutions:</strong>&nbsp;{{ chunk.ner_I.join(', ') }}
                  </q-badge>
                  <q-badge color="orange-1" text-color="orange-9" class="q-pa-sm" v-if="chunk.ner_M?.length">
                    <strong>Media:</strong>&nbsp;{{ chunk.ner_M.join(', ') }}
                  </q-badge>
                  <q-badge color="grey-2" text-color="grey-9" class="q-pa-sm" v-if="chunk.ner_O?.length">
                    <strong>Artifacts:</strong>&nbsp;{{ chunk.ner_O.join(', ') }}
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

  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, onBeforeUnmount, watch } from 'vue'
import { QPage, QForm, QInput, QBtn, QCard, QCardSection, QSeparator, QSelect, QCheckbox, QRange, QPagination, Notify } from 'quasar'
import type { SearchRequest, SearchResponse, SummaryResponse, TextChunkWithDocument } from 'src/models'
import type { Chunk2CollectionReq } from 'src/generated/api'
import { api } from 'src/boot/axios'
import { useApi } from 'src/composables/useApi'
import { useCollectionStore } from 'src/stores/chunk_collection-store'
import { useUserStore } from 'src/stores/user-store'
import useDocuments from 'src/composables/useDocuments'

// Search Form State
const showFilters = ref(false)
const showSummarizeOptions = ref(false)
const searchForm = ref<SearchRequest>({
  query: '',
  limit: 50, // Increased default to show pagination better
  user_collection_id: null,
  type: 'hybrid',
  search_title_generate: false,
  search_summary_generate: false,
  search_results_summary_generate: false,
  min_year: null,
  max_year: null,
  min_date: null,
  max_date: null,
  language: null,
  tag_uuids: [],
  positive: true,
  automatic: true
})

// Mock Filter Data State
const loadingFilters = ref(false)
const availableLanguages = ref<string[]>([])
const selectedLanguages = ref<string[]>([])
const languageCodeMap: Record<string, string> = {
  English: 'eng',
  Czech: 'ces',
  German: 'deu',
  Spanish: 'spa',
  French: 'fra'
}
const availableYears = ref({ min: 1800, max: 2026 })
const yearRange = ref({ min: 1800, max: 2026 })

// Results State
const loading = ref(false)
let searchResponse: SearchResponse | null = null
const results = ref<TextChunkWithDocument[]>([])
const selectedResults = ref<string[]>([])
const targetCollectionId = ref<string | null>(null)
const timeSpent = ref(0)
const searchLog = ref<string[]>([])
const lastSearchRequest = ref<SearchRequest | null>(null)

// Pagination State
const currentPage = ref(1)
const itemsPerPage = ref(10)
const totalPages = computed(() => Math.ceil(results.value.length / itemsPerPage.value))
const paginatedResults = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage.value
  return results.value.slice(start, start + itemsPerPage.value)
})

// Analysis Tools State
const brevityType = ref('short')
const brevityTypes = [
  { label: 'Short', value: 'short' },
  { label: 'Detailed', value: 'detailed' }
]

const summaryScopeDefault = 'broader'
const summaryScope = ref(summaryScopeDefault)
const scopeOptions = [
  { label: 'Focused', value: 'focused' },
  { label: 'Broader', value: 'broader' },
  { label: 'Extensive', value: 'extensive' },
  { label: 'Selected', value: 'selected' }
]

const scopeOptionsKMapping: Record<string, number | null> = {
  focused: 3,
  broader: 10,
  extensive: null // all of it
}

const summarizing = ref(false)
const summary = ref('')
const summaryTimeSpent = ref(0)
const highlightedDocNumber = ref<number | null>(null)
let clearHighlightTimer: number | null = null

const summarizedResultIndices = ref<number[]>([])

type SummaryToken =
  | { type: 'text'; value: string }
  | { type: 'citation'; docNumber: number }

function parseSummaryTokens (text: string, indicesMap: number[]): SummaryToken[] {
  const tokens: SummaryToken[] = []
  const citationRegex = /\[(doc([1-9][0-9]*))]/g
  let lastIndex = 0

  for (const match of text.matchAll(citationRegex)) {
    const matchText = match[0]
    const number = parseInt(match[2], 10)
    const index = match.index ?? 0

    if (index > lastIndex) {
      tokens.push({ type: 'text', value: text.slice(lastIndex, index) })
    }
    const translatedNumber = indicesMap[number - 1] ?? number
    tokens.push({ type: 'citation', docNumber: translatedNumber })

    lastIndex = index + matchText.length
  }

  if (lastIndex < text.length) {
    tokens.push({ type: 'text', value: text.slice(lastIndex) })
  }

  return tokens
}

const parsedSummaryTokens = computed(() => parseSummaryTokens(summary.value, summarizedResultIndices.value))

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
const collectionStore = useCollectionStore()
const userStore = useUserStore()
const apiClients = useApi()
const apiDocumentClient = useDocuments()

async function loadCollections () {
  if (!userStore.isLoggedIn || !userStore.getUserId) return

  collectionStore.setUser(userStore.getUserId)
  loading.value = true
  try {
    await collectionStore.fetchCollections(collectionStore.userId)
  } catch (err) {
    console.error(err)
    Notify.create({ message: 'Failed to load collections', position: 'top', color: 'negative' })
  } finally {
    loading.value = false
  }
}

watch(
  selectedResults,
  () => {
    if (selectedResults.value.length === 0) {
      summaryScope.value = summaryScopeDefault
    } else {
      summaryScope.value = 'selected'
    }
  }
)

watch(
  () => userStore.getUserId,
  async () => {
    await loadCollections()
  },
  { immediate: true }
)

const collectionOptions = computed(() =>
  collectionStore.collections.map(c => ({
    label: c.name ?? `Collection ${c.id}`,
    value: c.id
  }))
)

type ActiveFilterBadge = {
  key: string
  type: 'collection' | 'language' | 'year'
  icon: string
  label: string
  value?: string
}

const selectedCollectionLabel = computed(() => {
  if (!searchForm.value.user_collection_id) return null
  const option = collectionOptions.value.find(option => option.value === searchForm.value.user_collection_id)
  return option?.label ?? `Collection ${searchForm.value.user_collection_id}`
})

const isYearFilterActive = computed(() => (
  yearRange.value.min !== availableYears.value.min ||
  yearRange.value.max !== availableYears.value.max
))

const activeFilterBadges = computed<ActiveFilterBadge[]>(() => {
  const badges: ActiveFilterBadge[] = []

  if (searchForm.value.user_collection_id) {
    badges.push({
      key: `collection:${searchForm.value.user_collection_id}`,
      type: 'collection',
      icon: 'folder',
      label: selectedCollectionLabel.value ?? searchForm.value.user_collection_id
    })
  }

  selectedLanguages.value.forEach(language => {
    badges.push({
      key: `language:${language}`,
      type: 'language',
      icon: 'language',
      label: language,
      value: language
    })
  })

  if (isYearFilterActive.value) {
    badges.push({
      key: 'year',
      type: 'year',
      icon: 'event',
      label: `${yearRange.value.min}-${yearRange.value.max}`
    })
  }

  return badges
})

function removeFilterBadge (badge: ActiveFilterBadge) {
  if (badge.type === 'collection') {
    searchForm.value.user_collection_id = null
    return
  }

  if (badge.type === 'language' && badge.value) {
    selectedLanguages.value = selectedLanguages.value.filter(language => language !== badge.value)
    if (selectedLanguages.value.length === 0) {
      searchForm.value.language = null
    }
    return
  }

  if (badge.type === 'year') {
    yearRange.value = {
      min: availableYears.value.min,
      max: availableYears.value.max
    }
    searchForm.value.min_year = null
    searchForm.value.max_year = null
  }
}

// Methods

async function fetchFilterMocks () {
  loadingFilters.value = true
  try {
    // Mock backend calls to get available languages and max/min years
    await new Promise(resolve => setTimeout(resolve, 600))
    availableLanguages.value = ['English', 'Czech', 'German', 'Spanish', 'French']
    availableYears.value = { min: 1800, max: new Date().getFullYear() }
    yearRange.value = { min: 1800, max: new Date().getFullYear() }

    // Set initial bounds
    searchForm.value.min_year = yearRange.value.min
    searchForm.value.max_year = yearRange.value.max
  } finally {
    loadingFilters.value = false
  }
}

function updateYearFilters (val: { min: number; max: number }) {
  searchForm.value.min_year = val.min
  searchForm.value.max_year = val.max
}

async function onSearch () {
  loading.value = true
  results.value = []
  selectedResults.value = []
  summary.value = ''
  summaryTimeSpent.value = 0
  summarizedResultIndices.value = []
  currentPage.value = 1 // reset pagination
  searchResponse = null

  // Attach selected language codes to search payload
  const selectedLanguageCodes = selectedLanguages.value
    .map(lang => languageCodeMap[lang])
    .filter((code): code is string => Boolean(code))

  searchForm.value.language = selectedLanguageCodes.length > 0
    ? selectedLanguageCodes
    : null

  // so far only one language is supported
  if (searchForm.value.language && searchForm.value.language.length > 1) {
    Notify.create({ message: `Multiple languages filtering is not supported yet, selecting only one`, position: 'top', color: 'warning' })
    searchForm.value.language = [searchForm.value.language[0]]
  }
  if (searchForm.value.language) {
    searchForm.value.language = searchForm.value.language[0]
  }

  if (searchForm.value.min_year === availableYears.value.min) searchForm.value.min_year = null
  if (searchForm.value.max_year === availableYears.value.max) searchForm.value.max_year = null

  console.log('Submitting search with payload:', searchForm.value)
  try {
    console.log('Search will start')
    const { data } = await api.post<SearchResponse>('/search', searchForm.value)
    console.log('Search response received:', data)
    searchResponse = data
    results.value = data.results || []
    timeSpent.value = data.time_spent
    searchLog.value = data.search_log
    lastSearchRequest.value = data.search_request
    if (results.value.length === 0) {
      Notify.create({ message: 'No results found', position: 'top', color: 'info' })
    }
  } catch (e) {
    console.error(e)
    Notify.create({ message: 'Search failed', position: 'top', color: 'negative' })
    results.value = []
    searchResponse = null
  } finally {
    loading.value = false
  }
}

async function onSummarize () {
  if (!results.value.length || !lastSearchRequest.value || !searchResponse) return
  summarizing.value = true

  // select the focus
  const summarizeK = scopeOptionsKMapping[summaryScope.value]
  const scopedSearchResponse: SearchResponse = {
    ...searchResponse
  }

  let currentIndices: number[] = []

  if (summaryScope.value === 'selected') {
    if (selectedResults.value.length === 0) {
      Notify.create({ message: 'Please select at least one result for summarization.', position: 'top', color: 'warning' })
      summarizing.value = false
      return
    }
    scopedSearchResponse.results = []
    results.value.forEach((r, index) => {
      if (selectedResults.value.includes(r.id)) {
        scopedSearchResponse.results.push(r)
        currentIndices.push(index + 1)
      }
    })
  } else if (summarizeK !== null) {
    scopedSearchResponse.results = results.value.slice(0, summarizeK)
    currentIndices = scopedSearchResponse.results.map((_, i) => i + 1)
  } else {
    scopedSearchResponse.results = results.value
    currentIndices = results.value.map((_, i) => i + 1)
  }

  try {
    const { data } = await api.post<SummaryResponse>('/summarize/results', scopedSearchResponse)
    summarizedResultIndices.value = currentIndices
    summary.value = data.summary
    summaryTimeSpent.value = data.time_spent
  } catch (e) {
    summary.value = 'Failed to summarize.'
    summaryTimeSpent.value = 0
  } finally {
    summarizing.value = false
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
  for (const chunkId of selectedResults.value) {
    const chunk2CollectionReq: Chunk2CollectionReq = {
      collectionId: targetCollectionId.value as string,
      chunkId
    }
    try {
      const data = await apiClients.default.addChunk2CollectionApiUserCollectionChunksPost({ chunk2CollectionReq })
      if (data.created) successCount++
    } catch (e) {
      console.error(e)
    }
  }
  Notify.create({ message: `Added ${successCount} chunk(s) to collection`, position: 'top', color: 'positive' })
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
      .map(r => r.document_object.id)
      .filter(id => id !== undefined)
  )

  for (const documentId of docIds) {
    try {
      await apiDocumentClient.addDocToCollection(documentId, targetCollectionId.value)
      successCount++
    } catch (e) {
      console.error(e)
    }
  }
  Notify.create({ message: `Added ${successCount} document(s) to collection`, position: 'top', color: 'positive' })
}

onMounted(async () => {
  await fetchFilterMocks()
  await loadCollections()
})

onBeforeUnmount(() => {
  if (clearHighlightTimer !== null) {
    window.clearTimeout(clearHighlightTimer)
  }
})

</script>

<style scoped>
.citation-link {
  color: var(--q-primary);
  text-decoration: underline;
}

.citation-target-highlight {
  outline: 2px solid var(--q-secondary) !important;
  outline-offset: 0;
}

:deep(.active-filter-chip .q-chip__icon--remove) {
  margin-left: 5px;
}
</style>
