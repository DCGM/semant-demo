<template>
  <q-page :class="pageIdle ? 'q-pa-md bg-grey-1 flex flex-center' : 'q-pa-md bg-grey-1'">
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
              v-if="pending && !pageIdle"
              class="row no-wrap items-center q-mt-xs text-caption text-grey-8 pending-note"
              role="status"
              data-testid="search-pending"
            >
              <q-icon name="edit_note" size="18px" class="q-mr-xs" />
              <span class="col">Changes not applied yet. Press Enter or Search to apply them.</span>
              <q-btn flat dense no-caps size="sm" color="primary" label="Discard changes" @click="discardDraft" />
            </div>

            <div v-if="appliedChips.length" class="row items-center q-gutter-sm q-mt-sm" aria-label="Applied filters" data-testid="applied-filters">
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
              <q-btn flat dense no-caps color="primary" label="Clear all" data-testid="search-clear-all" @click="clearAllApplied" />
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

      <div v-if="!pageIdle">
        <!-- Results and Visualizations show the same applied criteria and results mode (#618). -->
        <q-tabs
          :model-value="view"
          dense
          no-caps
          inline-label
          align="left"
          active-color="primary"
          indicator-color="primary"
          class="explore-views q-mb-md"
          aria-label="Explore view"
          data-testid="explore-view"
          @update:model-value="chooseView"
        >
          <q-tab name="results" icon="list" label="Results" data-testid="view-results" />
          <q-tab name="visualizations" icon="insights" label="Visualizations" data-testid="view-visualizations" />
        </q-tabs>

        <!-- One results header for both modes: the mode switch keeps the applied criteria (#606). -->
        <div class="results-header">
          <div class="results-header__title">
            <div class="text-h5 text-weight-medium">{{ mode === 'documents' ? 'Documents' : 'Passages' }}</div>
            <div v-if="view === 'visualizations'" class="text-caption text-grey-7" data-testid="charts-unit">
              <template v-if="applied.criteria.textQuery">{{ mode === 'documents' ? 'Charts of the ranked documents of this search.' : 'Charts of the ranked passages of this search.' }}</template>
              <template v-else>{{ mode === 'documents' ? 'Charts of the matching documents.' : 'Charts of the matching passages.' }}</template>
            </div>
            <div v-else-if="resultsState === 'results'" class="text-caption text-grey-7" data-testid="search-coverage">
              {{ coverage }} Search completed in {{ timeSpent.toFixed(2) }}s.
            </div>
            <div v-else-if="resultsState === 'documents'" class="text-caption text-grey-7" data-testid="search-coverage">
              {{ coverage }} {{ documentOrder }}
            </div>
          </div>
          <q-btn-toggle
            :model-value="mode"
            :options="MODE_OPTIONS"
            no-caps
            unelevated
            dense
            toggle-color="primary"
            color="white"
            text-color="primary"
            class="results-mode"
            aria-label="Results mode"
            data-testid="results-mode"
            @update:model-value="chooseMode"
          />
        </div>

        <ExploreVisualizations
          v-if="view === 'visualizations'"
          :availability="chartsShown"
          :distributions="charts.distributions.value"
          :loading="charts.loading.value"
          :slow="charts.slow.value"
          :error="charts.error.value"
          :invalid="charts.invalid.value"
          :ranked="rankedState"
          @retry="charts.retry"
          @retry-ranked="resultCharts.retry"
          @retry-search="runApplied({ force: true })"
          @apply-period="applyPeriod"
          @inspect="inspect"
          @show-documents="chooseMode('documents')"
        />

        <!-- Results of a chart category (#620): a subset of the shown search's ranking, never a new search. -->
        <div v-else-if="inspecting" data-testid="inspection">
          <q-banner rounded class="inspection-banner q-mb-md" data-testid="inspection-banner">
            <template v-slot:avatar>
              <q-icon name="filter_center_focus" color="primary" />
            </template>
            <div class="text-subtitle2" data-testid="inspection-label">
              Inspecting the {{ mode === 'documents' ? 'documents' : 'passages' }} {{ inspectedLabel }}
            </div>
            <div v-if="inspectedList && rankedCounts" class="text-caption" data-testid="inspection-count">
              {{ inspectionCount(inspectedList.length, rankedCounts) }} of this search, in ranking order. Only the results
              this search ranked: nothing is searched again.
            </div>
            <template v-slot:action>
              <q-btn flat no-caps color="primary" icon="insights" label="Back to charts" data-testid="inspection-charts" @click="chooseView('visualizations')" />
              <q-btn flat no-caps color="primary" icon="close" label="Show all results" data-testid="inspection-clear" @click="stopInspecting" />
            </template>
          </q-banner>

          <div v-if="inspectionState === 'loading'" class="results-status column items-center q-pa-xl text-grey-8" role="status" data-testid="inspection-loading">
            <q-spinner color="primary" size="2.5em" />
            <div class="q-mt-sm">{{ activeLoading ? 'Searching…' : 'Loading the inspected results…' }}</div>
          </div>
          <q-banner v-else-if="inspectionState === 'error'" rounded class="bg-red-1 text-negative" role="alert" data-testid="inspection-error">
            <template v-slot:avatar>
              <q-icon name="error_outline" color="negative" />
            </template>
            {{ inspectionError }}
            <template v-if="!rankedState.invalid" v-slot:action>
              <q-btn flat color="negative" label="Try again" data-testid="inspection-retry" @click="retryInspection" />
            </template>
          </q-banner>
          <div v-else-if="inspectionState === 'unavailable'" class="results-status column items-center q-pa-xl text-grey-8" role="status" data-testid="inspection-unavailable">
            <q-icon name="block" size="2.5em" />
            <div class="q-mt-sm text-subtitle1">This corpus database does not record this property, so results cannot be inspected by it.</div>
          </div>
          <div v-else-if="inspectionState === 'empty'" class="results-status column items-center q-pa-xl text-grey-8" role="status" data-testid="inspection-empty">
            <q-icon name="search_off" size="2.5em" />
            <div class="q-mt-sm text-subtitle1">None of this search's results are in this category.</div>
            <div class="text-caption">Show all results, or go back to the charts and inspect another category.</div>
          </div>
          <div v-else-if="inspectionState === 'gone'" class="results-status column items-center q-pa-xl text-grey-8" role="status" data-testid="inspection-gone">
            <q-icon name="search_off" size="2.5em" />
            <div class="q-mt-sm text-subtitle1">These results no longer exist or no longer match the search's filters.</div>
            <div class="text-caption">Search again to rank the current corpus.</div>
          </div>
          <template v-else>
            <div class="q-gutter-y-md">
              <template v-if="mode === 'documents'">
                <DocumentResultCard
                  v-for="item in inspection.documents.value"
                  :id="`document-${rankOf.get(item.document.id)}`"
                  :key="item.document.id"
                  :hit="item"
                  :number="rankOf.get(item.document.id) ?? 0"
                />
              </template>
              <template v-else>
                <SearchResultCard
                  v-for="chunk in inspection.passages.value"
                  :id="`result-${rankOf.get(chunk.id)}`"
                  :key="chunk.id"
                  :chunk="chunk"
                  :number="rankOf.get(chunk.id) ?? 0"
                  :filters="availableSearchFilters"
                  :selectable="false"
                  :highlighted="highlightedDocNumber === rankOf.get(chunk.id)"
                  :context-shown="contextResultNumber === rankOf.get(chunk.id)"
                  @view-context="viewContext(chunk, rankOf.get(chunk.id) ?? 0)"
                />
              </template>
            </div>
            <div class="column items-center q-mt-xl q-gutter-y-sm">
              <q-banner v-if="inspection.loadMoreError.value" dense rounded class="bg-red-1 text-negative" role="alert">
                {{ inspection.loadMoreError.value }}
              </q-banner>
              <q-btn
                v-if="inspection.hasMore()"
                outline
                color="primary"
                icon="expand_more"
                label="Load more inspected results"
                :loading="inspection.loadingMore.value"
                data-testid="inspection-load-more"
                @click="inspection.loadMore"
              />
            </div>
          </template>
        </div>

        <div v-else-if="resultsState === 'loading'" class="results-status column items-center q-pa-xl text-grey-8" role="status" data-testid="search-loading">
          <q-spinner color="primary" size="2.5em" />
          <div class="q-mt-sm">{{ mode === 'documents' ? 'Loading documents…' : 'Searching passages…' }}</div>
        </div>

        <q-banner v-else-if="resultsState === 'error'" rounded class="bg-red-1 text-negative" role="alert" data-testid="search-error">
          <template v-slot:avatar>
            <q-icon name="error_outline" color="negative" />
          </template>
          Search failed: {{ activeError }}
          <template v-slot:action>
            <q-btn flat color="negative" label="Try again" @click="runApplied({ force: true })" />
          </template>
        </q-banner>

        <div v-else-if="resultsState === 'empty'" class="results-status column items-center q-pa-xl text-grey-8" role="status" data-testid="search-empty">
          <q-icon name="search_off" size="2.5em" />
          <template v-if="mode === 'documents'">
            <div class="q-mt-sm text-subtitle1">{{ applied.criteria.textQuery ? 'No documents match this search.' : 'No documents match these filters.' }}</div>
            <div class="text-caption">{{ applied.criteria.textQuery ? 'Try other words, or remove some of the filters above.' : 'Remove some of the filters above.' }}</div>
          </template>
          <template v-else>
            <div class="q-mt-sm text-subtitle1">No passages match this search.</div>
            <div class="text-caption">Try other words, or remove some of the filters above.</div>
          </template>
        </div>

        <div v-else-if="resultsState === 'needsQuery'" class="results-status column items-center q-pa-xl text-grey-8" role="status" data-testid="search-needs-query">
          <q-icon name="manage_search" size="2.5em" />
          <div class="q-mt-sm text-subtitle1">Enter a text query to search passages with these filters.</div>
          <div class="text-caption">Browsing passages by filters alone is not available. Documents lists the documents these filters match.</div>
        </div>

        <div v-else-if="resultsState === 'documents'">
          <div class="q-gutter-y-md">
            <DocumentResultCard
              v-for="(item, index) in documentItems"
              :id="`document-${index + 1}`"
              :key="item.document.id"
              :hit="item"
              :number="index + 1"
            />
          </div>
          <div class="column items-center q-mt-xl q-gutter-y-sm">
            <q-banner v-if="documents.loadMoreError.value" dense rounded class="bg-red-1 text-negative" role="alert">
              {{ documents.loadMoreError.value }}
            </q-banner>
            <q-btn
              v-if="hasMore"
              outline
              color="primary"
              icon="expand_more"
              label="Load more documents"
              :loading="documents.loadingMore.value"
              data-testid="search-load-more"
              @click="documents.loadMore"
            />
          </div>
        </div>

        <div v-else-if="resultsState === 'results'">
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

    </div>

    <RightSidebarPanel v-if="results.length || passages.loading.value" id="search-summary" label="Summary" icon="summarize">
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
import { QPage, QForm, QInput, QBtn, QBtnToggle, QCard, QCardSection, QSeparator, QSelect, QRange, QItem, QItemSection, QItemLabel, QBanner, QSpinner, QTabs, QTab, Notify, useQuasar } from 'quasar'
import { SearchType, WriteOutcome, type SearchFilter, type SearchVectorInfo } from 'src/generated/api'
import { captureSession, useApi } from 'src/shared/api'
import { useUserStore } from 'src/features/auth/userStore'
import { useUserCollectionsStore } from 'src/features/user_collections/userCollectionsStore'
import { useDocumentsStore } from 'src/features/documents/documentsStore'
import { collectionRights } from 'src/features/user_collections/permissions'
import { criteriaKey, effectiveMode, emptyCriteria, emptyLocation, locationKey, MAX_TEXT_QUERY_LENGTH, normalizeCriteria, sameCriteria, hasFilters, type Criteria, type ExploreLocation, type ExploreView, type Inspection, type ResultsMode } from 'src/features/explore/criteria'
import { useExploreLocation, type AppliedReason } from 'src/features/explore/useExploreLocation'
import { hasMorePassages, passageCoverage, usePassageSearch } from 'src/features/explore/usePassageSearch'
import { documentCoverage, documentOrderLabel, hasMoreDocuments, useDocumentSearch } from 'src/features/explore/useDocumentSearch'
import { chartsAvailability, useExploreCharts } from 'src/features/explore/useExploreCharts'
import {
  documentPopulation, inspectedMembers, inspectionCount, inspectionLabel, passagePopulation, useResultCharts,
  type RankedChartsState, type RankedPopulation
} from 'src/features/explore/useResultCharts'
import { useResultInspection, type InspectedSubset } from 'src/features/explore/useResultInspection'
import ExploreVisualizations from 'src/features/explore/ExploreVisualizations.vue'
import type { YearWindow } from 'src/features/analytics/timeline'
import { useSearchSummary } from './useSearchSummary'
import SearchSummaryPanel from './SearchSummaryPanel.vue'
import SearchResultCard from './SearchResultCard.vue'
import DocumentResultCard from './DocumentResultCard.vue'
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
// Passages (`POST /api/search/passages`) for a text query, and Documents (`POST /api/search/documents`)
// for filters alone (#606) or ranked by a text query (#607), each loaded page by page. The
// Visualizations view (#618) charts the same applied criteria: for Documents without a text
// query, every matching document (`useExploreCharts`); for a text query, exactly the results its
// search ranked (`useResultCharts`, #620), whose chart categories can be inspected in Results
// (`inspect` in the URL: a subset of the same ranking, `useResultInspection`). Switching between
// the views searches or counts again only when the shown ones are of other criteria.

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

// Results: the passages or the documents of the applied search, as loaded so far.
const mode = computed<ResultsMode>(() => effectiveMode(applied.value))
const MODE_OPTIONS = [
  { label: 'Documents', value: 'documents', attrs: { 'data-testid': 'results-mode-documents' } },
  { label: 'Passages', value: 'passages', attrs: { 'data-testid': 'results-mode-passages' } }
]
const passages = usePassageSearch()
const documents = useDocumentSearch()
const loading = computed(() => passages.loading.value || documents.loading.value)
const results = computed(() => passages.results.value?.items ?? [])
const documentItems = computed(() => documents.results.value?.items ?? [])
const activeError = computed(() => (mode.value === 'documents' ? documents.error.value : passages.error.value))
const timeSpent = computed(() => passages.results.value?.timeSpent ?? 0)
const coverage = computed(() => {
  if (mode.value === 'documents') return documents.results.value ? documentCoverage(documents.results.value) : ''
  return passages.results.value ? passageCoverage(passages.results.value) : ''
})
const documentOrder = computed(() => (documents.results.value ? documentOrderLabel(documents.results.value) : ''))
const hasMore = computed(() => {
  if (mode.value === 'documents') return documents.results.value ? hasMoreDocuments(documents.results.value) : false
  return passages.results.value ? hasMorePassages(passages.results.value) : false
})
const searchContext = computed<SearchResultsContext | null>(() => {
  const current = passages.results.value
  return current
    ? { id: current.id, query: current.query.criteria.textQuery ?? '', results: current.items, timeSpent: current.timeSpent }
    : null
})
const selectedResults = ref<string[]>([])
const targetCollectionId = ref<string | null>(null)

/** Nothing is applied: no criteria, no chosen results mode or view (the page as first opened). */
const isIdleLocation = (location: ExploreLocation) =>
  !location.criteria.textQuery && !hasFilters(location.criteria) && location.mode === null && location.view === null

// Views: Results or Visualizations of the applied criteria, kept in the URL (`view`).
const view = computed<ExploreView>(() => applied.value.view ?? 'results')
const charts = useExploreCharts()
const chartsShown = computed(() => chartsAvailability(applied.value.criteria, mode.value, appliedCollection.value))

// Charts of a text query's results (#620): the counts of the ranking the Results hold.
const resultCharts = useResultCharts()
const inspection = useResultInspection()
const activeLoading = computed(() => (mode.value === 'documents' ? documents.loading.value : passages.loading.value))

/** The ranking of the applied text query in the shown mode, once its search answered. */
const rankedPopulation = computed<RankedPopulation | null>(() => {
  const location = applied.value
  if (!location.criteria.textQuery) return null
  const population = mode.value === 'documents'
    ? (documents.results.value ? documentPopulation(documents.results.value) : null)
    : (passages.results.value ? passagePopulation(passages.results.value) : null)
  // Results of other criteria (a search not run yet) are never charted as these.
  const same = population && criteriaKey(population.criteria) === criteriaKey(location.criteria) &&
    population.vector === location.vector && population.userCollectionId === appliedCollection.value
  return same ? population : null
})
/** Results show the inspected category of a chart: a text query's ranking only. */
const inspecting = computed(() => view.value === 'results' && applied.value.inspect !== null && !!applied.value.criteria.textQuery)
/** The counts are needed: the charts are shown, or a category of them is inspected. */
const rankedNeeded = computed(() => view.value === 'visualizations' || inspecting.value)
watch([rankedPopulation, rankedNeeded], ([population, needed]) => {
  if (population && needed) void resultCharts.show(population)
})
const rankedCurrent = computed(() => !!rankedPopulation.value && resultCharts.population.value?.key === rankedPopulation.value.key)
const rankedCounts = computed(() => (rankedCurrent.value ? resultCharts.distributions.value : null))
const rankedState = computed<RankedChartsState>(() => {
  const vector = rankedCounts.value?.ranking.vector ?? null
  return {
    searching: activeLoading.value,
    searchError: activeError.value,
    counts: rankedCounts.value,
    slow: resultCharts.slow.value,
    error: rankedCurrent.value ? resultCharts.error.value : null,
    invalid: rankedCurrent.value && resultCharts.invalid.value,
    vectorName: vector ? (availableVectors.value.find(v => v.id === vector)?.name ?? vector) : null
  }
})

const inspectedLabel = computed(() => (applied.value.inspect ? inspectionLabel(applied.value.inspect) : ''))
/** The counted results of the inspected category; null until counted or when the property is not recorded. */
const inspectedList = computed(() => (inspecting.value && rankedCounts.value && applied.value.inspect
  ? inspectedMembers(rankedCounts.value, applied.value.inspect)
  : null))
const inspectedSubset = computed<InspectedSubset | null>(() => {
  const population = rankedPopulation.value
  const members = inspectedList.value
  const picked = applied.value.inspect
  if (!population || !members || !picked) return null
  const key = `${population.key}|${picked.dimension}:${picked.value}`
  const base = { key, criteria: population.criteria, userCollectionId: population.userCollectionId }
  if (population.mode === 'documents') {
    const entries = new Map((documents.results.value?.ranked ?? []).map(entry => [entry.id, entry]))
    return { ...base, documents: members.flatMap(m => entries.get(m.id) ?? []), passageIds: null }
  }
  return { ...base, documents: null, passageIds: members.map(m => m.id) }
})
watch(inspectedSubset, (subset) => {
  if (subset) void inspection.open(subset)
  else if (!inspecting.value) inspection.clear()
})
/** Ranking position of each ranked id (1-based), as Results number them. */
const rankOf = computed(() => new Map((rankedPopulation.value?.ids ?? []).map((id, index) => [id, index + 1])))
const inspectionError = computed(() => {
  if (activeError.value) return `Search failed: ${activeError.value}`
  if (rankedState.value.error) return `The search results could not be counted: ${rankedState.value.error}`
  return inspection.error.value
})
const inspectionState = computed<'loading' | 'error' | 'unavailable' | 'empty' | 'gone' | 'items'>(() => {
  if (inspectionError.value) return 'error'
  if (!rankedCounts.value) return 'loading'
  if (inspectedList.value === null) return 'unavailable'
  if (!inspectedList.value.length) return 'empty'
  if (inspection.loading.value || inspection.subset.value?.key !== inspectedSubset.value?.key) return 'loading'
  const shown = mode.value === 'documents' ? inspection.documents.value.length : inspection.passages.value.length
  return shown || inspection.hasMore() ? 'items' : 'gone'
})

function retryInspection () {
  if (activeError.value) void runApplied({ force: true })
  else if (rankedState.value.error) void resultCharts.retry()
  else void inspection.retry()
}

/** Shows a chart category's results of the same ranking in Results: a new history entry. */
function inspect (picked: Inspection) {
  void explore.apply({ ...applied.value, view: null, inspect: picked })
}

function stopInspecting () {
  void explore.apply({ ...applied.value, inspect: null })
}

/**
 * What the results area shows: passage cards (`results`), document cards (`documents`) or a
 * state. Without a text query Passages need one (`needsQuery`); Documents take both (#607).
 */
const resultsState = computed<'results' | 'documents' | 'loading' | 'error' | 'empty' | 'needsQuery' | 'idle'>(() => {
  const location = applied.value
  if (isIdleLocation(location)) return 'idle'
  if (mode.value === 'documents') {
    if (documents.loading.value) return 'loading'
    if (documents.error.value) return 'error'
    if (documents.results.value) return documentItems.value.length ? 'documents' : 'empty'
    return 'idle'
  }
  if (!location.criteria.textQuery) return 'needsQuery'
  if (passages.loading.value) return 'loading'
  if (passages.error.value) return 'error'
  if (passages.results.value) return results.value.length ? 'results' : 'empty'
  return 'idle'
})

/** The page as first opened (only the form), or Results with nothing to show. */
const pageIdle = computed(() => view.value === 'results' && resultsState.value === 'idle')

/** The results mode a location shows without a choice: Passages for a text query, else Documents. */
const defaultMode = (criteria: Criteria): ResultsMode => (criteria.textQuery ? 'passages' : 'documents')

/** Shows the applied criteria in another results mode: a new history entry, the same criteria. */
function chooseMode (chosen: ResultsMode) {
  if (chosen === mode.value) return
  const criteria = applied.value.criteria
  // The default mode is not kept in the URL, so a later search picks the default for its criteria.
  void explore.apply({ ...applied.value, mode: chosen === defaultMode(criteria) ? null : chosen, inspect: null })
}

/** Shows the applied criteria in the other view: a new history entry, the same criteria and mode. */
function chooseView (chosen: ExploreView) {
  if (chosen === view.value) return
  // An inspected category is a part of Results; either view shows the whole ranking again.
  const location: ExploreLocation = { ...applied.value, view: chosen === 'results' ? null : chosen, inspect: null }
  // Back in Results, no criteria list every document rather than show the page as first opened.
  if (isIdleLocation(location)) location.mode = 'documents'
  void explore.apply(location)
}

/**
 * Applies a timeline period as the publication-year filter, keeping the other criteria; the
 * draft gets the same years and keeps its other changes.
 */
function applyPeriod (period: YearWindow) {
  const years = { yearMin: period.start, yearMax: period.end }
  const criteria = applied.value.criteria
  draftFilters.value = normalizeCriteria({ ...draftFilters.value, documentFilters: { ...draftFilters.value.documentFilters, ...years } })
  void explore.apply({ ...applied.value, inspect: null, criteria: normalizeCriteria({ ...criteria, documentFilters: { ...criteria.documentFilters, ...years } }) })
}

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
  // The loaded results, or the inspected ones (#620), are numbered by their ranking position.
  if (!document.getElementById(`result-${docNumber}`)) {
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
      documents.cancel()
      selectedResults.value = []
      draftCollection.value = null
      appliedCollection.value = null
      targetCollectionId.value = null
      // Without the collection scope the Visualizations may chart the public corpus now: count
      // the applied criteria rather than keep the collection's state or an unanswered spinner.
      if (view.value === 'visualizations' || inspecting.value) void runApplied()
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
  const location: ExploreLocation = { ...applied.value, inspect: null }
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
  // Without its last filter, a documents search lists every document rather than nothing.
  if (isIdleLocation(location) && mode.value === 'documents') location.mode = 'documents'
  void explore.apply(location)
}

/**
 * Removes every applied chip at once: the filters, the collection and the search vector (not the
 * text query), from the draft too, and applies the result.
 */
function clearAllApplied () {
  clearAllFilters()
  appliedCollection.value = null
  const location: ExploreLocation = { ...applied.value, criteria: normalizeCriteria({ textQuery: applied.value.criteria.textQuery }), vector: null, inspect: null }
  if (isIdleLocation(location) && mode.value === 'documents') location.mode = 'documents'
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

/**
 * Applies the draft: a new history entry, or the same search again when nothing changed.
 * A text query searches Passages, filters alone list Documents (an empty form: every document).
 * Documents chosen for a text query stay for the next text query (#607); Passages need one,
 * so criteria without it show Documents.
 */
async function onSearch () {
  history.close()
  const criteria = draftCriteria.value
  if (criteria.textQuery && criteria.textQuery.length > MAX_TEXT_QUERY_LENGTH) {
    Notify.create({ message: `The text query can be at most ${MAX_TEXT_QUERY_LENGTH.toLocaleString('en')} characters long.`, position: 'top', color: 'warning' })
    return
  }
  // The empty criteria keep the mode in the URL, which tells them apart from the page as first opened.
  // Documents chosen for a text query stay for the next one (#607); browsing by filters alone
  // shows Documents by default only, so a text query added there searches Passages.
  const keepDocuments = Boolean(applied.value.criteria.textQuery) && applied.value.mode === 'documents'
  const chosen = (!criteria.textQuery && !hasFilters(criteria)) || (criteria.textQuery && keepDocuments)
    ? 'documents'
    : null
  appliedCollection.value = draftCollection.value
  await explore.apply({ ...applied.value, criteria, mode: chosen, vector: draftVector.value, inspect: null })
}

// The applied location runs once the search options are loaded: a link's values are checked
// against them first, so an unknown filter or vector is reported instead of searched.
let waitingForOptions = false
let waitingForce = false

/** The search the Results show (null: none or cancelled); a view switch keeps it. */
let resultsKey: string | null = null
const resultsKeyOf = (location: ExploreLocation) =>
  JSON.stringify([criteriaKey(location.criteria), effectiveMode(location), location.vector, appliedCollection.value])

/** The Results hold (or are loading) the answer of their last search, not an error or nothing. */
function resultsCurrent (location: ExploreLocation): boolean {
  if (effectiveMode(location) === 'documents') {
    return isIdleLocation(location) || (!documents.error.value && (documents.loading.value || documents.results.value !== null))
  }
  if (!location.criteria.textQuery) return true
  return !passages.error.value && (passages.loading.value || passages.results.value !== null)
}

/**
 * `again`: the applied location was applied unchanged (Search with the same criteria, or a
 * changed collection scope), which searches or counts again.
 */
function onApplied (location: ExploreLocation, { reason, invalid }: { reason: AppliedReason, invalid: string[] }, again = false) {
  if (invalid.length) {
    Notify.create({ message: `Left out of the search because they are not valid: ${invalid.join(', ')}`, position: 'top', color: 'warning' })
  }
  if (reason === 'navigation') {
    // Back/Forward or a link: the form shows the applied search, the collection scope stays.
    setDraft(location)
    draftCollection.value = appliedCollection.value
  }
  // The selection belongs to the shown results, which a view switch keeps.
  if (again || resultsKeyOf(location) !== resultsKey) selectedResults.value = []
  void runApplied({ force: again })
}

async function runApplied ({ force = false } = {}) {
  if (filtersStatus.value === 'loading' || vectorsStatus.value === 'loading') {
    waitingForOptions = true
    waitingForce ||= force
    return
  }
  force ||= waitingForce
  waitingForOptions = false
  waitingForce = false
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
  if (location.inspect && (!location.criteria.textQuery || location.view === 'visualizations')) {
    // Only Results of a text query's ranking can be inspected.
    dropped.push('Inspected results')
    corrected.inspect = null
  }
  if (dropped.length) {
    Notify.create({ message: `Left out of the search because they are not available: ${dropped.join(', ')}`, position: 'top', color: 'warning' })
    setDraft(corrected)
    await explore.apply(corrected, { replace: true }) // runs the corrected search
    return
  }

  // A text query's charts count the ranking of its search: searched as for Results (#620).
  const ranked = chartsAvailability(location.criteria, effectiveMode(location), appliedCollection.value) === 'ranked'
  if (location.view === 'visualizations' && !ranked) {
    // The Results are searched when shown; a search of other criteria is not finished meanwhile.
    if (resultsKeyOf(location) !== resultsKey) {
      passages.cancel()
      documents.cancel()
      resultsKey = null
    }
    if (chartsAvailability(location.criteria, effectiveMode(location), appliedCollection.value) === 'documents') {
      charts.show(location.criteria, { force })
    }
    return
  }
  const key = resultsKeyOf(location)
  if (!force && key === resultsKey && resultsCurrent(location)) return
  resultsKey = key
  resultCharts.clear()
  inspection.clear()

  if (effectiveMode(location) === 'documents') {
    passages.cancel()
    if (isIdleLocation(location)) documents.cancel()
    else await documents.search({ criteria: location.criteria, vector: location.vector, userCollectionId: appliedCollection.value })
    return
  }
  documents.cancel()
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
  const again = details.reason === 'apply' && locationKey(location) === locationKey(applied.value)
  applied.value = location
  onApplied(location, details, again)
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
  documents.cancel()
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

/* Padding, not a margin: a margin would collapse with the result list's negative gutter. */
.results-header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 8px 16px;
  padding-bottom: 16px;
}

.results-header__title {
  min-width: 0;
  flex: 1 1 260px;
}

.results-mode {
  border: 1px solid var(--q-primary);
}

.explore-views {
  border-bottom: 1px solid rgba(0, 0, 0, 0.12);
}

.results-status {
  min-height: 160px;
  text-align: center;
}

:deep(.active-filter-chip .q-chip__icon--remove) {
  margin-left: 5px;
}
</style>
