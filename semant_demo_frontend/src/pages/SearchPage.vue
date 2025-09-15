<template>
  <q-page class="q-pa-md">
    <q-form @submit.prevent="onSearch">
      <div class="row q-col-gutter-md">
        <div class="col">
          <q-input v-model="searchForm.query" label="Search Query" dense outlined required />
        </div>
        <div class="col">
          <q-input v-model.number="searchForm.limit" type="number" label="Limit" dense outlined :min="1" :max="50" />
        </div>
        <div class="col">
          <q-input v-model="searchForm.language" label="Language" dense outlined />
        </div>
        <div class="col">
          <q-input v-model.number="searchForm.min_year" type="number" label="Min Year" dense outlined />
        </div>
        <div class="col">
          <q-input v-model.number="searchForm.max_year" type="number" label="Max Year" dense outlined />
        </div>
        <div class="col-auto flex flex-center">
          <q-btn type="submit" color="primary" label="Search" :loading="loading" />
        </div>
      </div>
    </q-form>

    <div v-if="results.length" class="q-mb-md">
      <div v-if="summaries.length" class="q-mb-lg">
        <div v-for="(item, idx) in summaries" :key="idx" class="q-mb-md">
          <q-card style="min-width:350px;max-width:600px;margin:auto;">
            <q-card-section>
              <div class="text-h6" v-if="item.question">Q: {{ item.question }}</div>
              <div class="text-h6" v-else>Summary</div>
              <div class="text-caption text-grey">Time spent: {{ item.timeSpent.toFixed(2) }}s</div>
            </q-card-section>
            <q-separator />
            <q-card-section>
              <div>{{ item.summary }}</div>
            </q-card-section>
          </q-card>
        </div>
      </div>
      <div class="q-pa-sm bg-grey-2 rounded-borders" style="max-width: 700px; margin: auto;">
        <div class="row items-center q-gutter-sm q-mb-sm">
          <q-select
            v-model="summaryType"
            :options="summaryTypes"
            label="Summary Type"
            dense
            outlined
            style="min-width: 150px"
          />
          <q-btn
            color="secondary"
            label="Summarize"
            :loading="summarizing"
            @click="onSummarize"
          />
        </div>
        <div class="row items-center q-gutter-sm">
          <q-input
            v-model="questionInput"
            label="Ask a question about these results"
            dense
            outlined
            style="flex:1;"
            @keyup.enter="onAskQuestion"
          />
          <q-btn
            color="primary"
            label="Send"
            :loading="asking"
            @click="onAskQuestion"
          />
        </div>
        <!-- Filter by tag -->
        <div class="row items-center q-gutter-sm">
          <div class="col">
            <div class="row items-center q-gutter-sm">
              <div class="text-caption q-mb-sm">Filter by Tags</div>
                <q-checkbox
                  v-model="tagFilterModes.positive"
                  label="Positive"
                  dense
                />
                <q-checkbox
                  v-model="tagFilterModes.automatic"
                  label="Automatic"
                  dense
                  class="q-ml-md"
                />
              </div>
            <div v-for="(example, index) in tagFormManage.tag_uuids" :key="index" class="row items-center q-mb-sm">
              <q-select
                v-model="tagFormManage.tag_uuids[index]"
                :options="tags"
                option-label="tag_name"
                option-value="tag_uuid"
                type="text"
                label="Tag"
                class="col"
                emit-value
                map-options
                dense
                outlined
                :loading="loadingSpinner"
                @popup-show="fetchTags"
              >
                <!-- No option slot -->
                <template v-slot:no-option>
                  <q-item>
                    <q-item-section class="text-grey">
                      No tags found
                    </q-item-section>
                  </q-item>
                </template>
                <!-- Custom option rendering -->
                <template v-slot:option="scope">
                  <q-item v-bind="scope.itemProps">
                    <q-item-section avatar>
                      <div
                        class="color-swatch"
                        :style="{ backgroundColor: scope.opt.tag_color }"
                      ></div>
                    </q-item-section>
                    <q-item-section avatar>
                      <q-item-label>{{ scope.opt.tag_pictogram }}</q-item-label>
                      <q-icon :name="scope.opt.tag_pictogram" />
                    </q-item-section>
                    <q-item-section>
                      <q-item-label>{{ scope.opt.tag_name }}</q-item-label>
                    </q-item-section>
                    <q-item-section>
                      <q-item-label> Definition: </q-item-label>
                      <q-item-label caption>
                        {{ scope.opt.tag_definition }}
                      </q-item-label>
                    </q-item-section>
                    <q-item-section>
                      <q-item-label> Examples: </q-item-label>
                      <div v-for="(example, index) in scope.opt.tag_examples" :key="index" class="row items-center q-mb-sm">
                        <q-item-label caption>
                          {{ example }}
                        </q-item-label>
                      </div>
                    </q-item-section>
                    <q-item-section>
                      <q-item-label> Collection name: </q-item-label>
                      <q-item-label caption>
                        {{ scope.opt.collection_name }}
                      </q-item-label>
                    </q-item-section>
                    <q-item-section>
                      <q-item-label> Tag uuid: </q-item-label>
                      <q-item-label caption>
                        {{ scope.opt.tag_uuid }}
                      </q-item-label>
                    </q-item-section>
                  </q-item>
                </template>

                <!-- Custom selected rendering -->
                <template v-slot:selected>
                  <q-item v-if="tagFormManage.tag_uuids[index]">
                    <q-item-section avatar>
                      <div
                        class="color-swatch"
                        :style="{ backgroundColor: tags.find(t => t.tag_uuid === tagFormManage.tag_uuids[index])?.tag_color }"
                      ></div>
                    </q-item-section>
                    <q-item-section avatar>
                      <q-item-label>{{ tags.find(t => t.tag_uuid === tagFormManage.tag_uuids[index])?.tag_pictogram }}</q-item-label>
                      <q-icon :name="tags.find(t => t.tag_uuid === tagFormManage.tag_uuids[index])?.tag_pictogram" />
                    </q-item-section>
                    <q-item-section >
                      <q-item-label caption> Name: </q-item-label>
                      <q-item-label> {{ tags.find(t => t.tag_uuid === tagFormManage.tag_uuids[index])?.tag_name }} </q-item-label>
                    </q-item-section>
                    <q-item-section class="col-grow">
                      <q-item-label caption>Tag uuid:</q-item-label>
                      <q-item-label caption class="text-mono">
                        {{ tagFormManage.tag_uuids[index] }}
                      </q-item-label>
                    </q-item-section>
                  </q-item>
                </template>
              </q-select>
              <q-btn
                v-if="tagFormManage.tag_uuids.length > 1"
                @click="removeTag(index)"
                icon="fa fa-close"
                color="negative"
                flat
                dense
                class="q-ml-sm"
              />
            </div>
            <div class="row items-center q-gutter-sm">
              <q-btn
                @click="addTag"
                v-if="tagsLen > tagFormManage.tag_uuids.length"
                icon="add"
                label="Add Another Tag"
                color="primary"
                outline
                dense
              />
            <q-space />
              <q-btn
                color="primary"
                label="Filter by tag(s)"
                :loading="loading"
                :disable="!tagFilterModes.positive && !tagFilterModes.automatic"
                @click="onFilterByTag"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="results.length" class="q-mt-lg">
      <div class="q-pa-sm row items-center q-gutter-sm">
        <div class="text-h6">Results ({{ results.length }})</div>
        <div class="text-caption text-grey q-ml-md">
          Time spent: {{ timeSpent.toFixed(2) }}s
        </div>
        <q-btn flat size="sm" color="primary" @click="toggleSelectAll">
          {{ allSelected ? 'Unselect All' : 'Select All' }}
        </q-btn>
      </div>
      <q-list bordered separator class="q-mt-md">
        <q-item
          v-for="(chunk, index) in results"
          :key="chunk.id"
          clickable
          class="q-pa-sm"
        >
          <q-item-section side top>
            <q-checkbox v-model="selectedResults" :val="chunk.id" />
          </q-item-section>
          <q-item-section>
            <div class="text-h6">{{ index + 1 }}. {{ chunk.query_title || chunk.title }}</div>
            <div class="text-caption text-grey">
              {{ chunk.document_object.author || 'Unknown Author' }}
              |
              {{ chunk.document_object.yearIssued || 'Year N/A' }}
            </div>
            <div class="text-caption">
              Doc Title: {{ chunk.document_object.title || 'N/A' }}
              |
              Language: {{ chunk.language || 'N/A' }}
            </div>
            <div class="text-caption text-grey">
              Pages: {{ chunk.from_page }}–{{ chunk.to_page }}
            </div>

            <!-- Show query_summary if available -->
            <div v-if="chunk.query_summary" class="q-mt-sm bg-grey-3 q-pa-sm rounded-borders">
              <strong>Summary:</strong> {{ chunk.query_summary }}
            </div>

            <!-- Always show text -->
            <div style="white-space: pre-wrap; margin-top: 0.5rem;">
              {{ chunk.text }}
            </div>

            <!-- NER only when present -->
            <div class="text-caption q-mt-sm">
              <div v-if="chunk.ner_P && chunk.ner_P.length">
                <strong>People:</strong> {{ chunk.ner_P.join(', ') }}
              </div>
              <div v-if="chunk.ner_G && chunk.ner_G.length">
                <strong>Places:</strong> {{ chunk.ner_G.join(', ') }}
              </div>
              <div v-if="chunk.ner_I && chunk.ner_I.length">
                <strong>Institutions:</strong> {{ chunk.ner_I.join(', ') }}
              </div>
              <div v-if="chunk.ner_M && chunk.ner_M.length">
                <strong>Media:</strong> {{ chunk.ner_M.join(', ') }}
              </div>
              <div v-if="chunk.ner_O && chunk.ner_O.length">
                <strong>Artifacts:</strong> {{ chunk.ner_O.join(', ') }}
              </div>
            </div>

            <!-- Tags -->
            <div class="text-caption q-mt-sm">
              <div v-if="tagFilterModes.positive && chunk.positiveTags && chunk.positiveTags.length">
                <strong>Positive tags:</strong>
                <div v-for="tag in chunk.positiveTags" :key="tag.tag_uuid" class="q-mb-md">
                  <div class="row items-center col-auto">
                    <div class="color-swatch" :style="{ backgroundColor: tag.tag_color }"></div>
                    <q-icon :name="tag.tag_pictogram" />
                    <q-label class="q-mr-sm">{{ tag.tag_name }}</q-label>
                    <q-label class="q-mr-sm">Definition: {{ tag.tag_definition }}</q-label>
                    <div class="text-caption q-mt-sm">Tag id: {{ tag.tag_uuid }}</div>
                  </div>
                </div>
              </div>
              <div v-if="tagFilterModes.automatic && chunk.automaticTags && chunk.automaticTags.length">
                <strong>Automatic tags:</strong>
                <div v-for="tag in chunk.automaticTags" :key="tag.tag_uuid" class="q-mb-md">
                  <div class="row items-center col-auto">
                    <div class="color-swatch" :style="{ backgroundColor: tag.tag_color }"></div>
                    <q-icon :name="tag.tag_pictogram" />
                    <q-label class="q-mr-sm">{{ tag.tag_name }}</q-label>
                    <q-label class="q-mr-sm">Definition: {{ tag.tag_definition }}</q-label>
                    <div class="text-caption q-mt-sm">Tag id: {{ tag.tag_uuid }}</div>
                  </div>
                </div>
              </div>
            </div>
          </q-item-section>
        </q-item>
      </q-list>
    </div>

    <q-dialog v-model="showSummary">
      <q-card style="min-width:350px;max-width:600px">
        <q-card-section>
          <div class="text-h6">Summary</div>
          <div class="text-caption text-grey">Time spent: {{ summaryTimeSpent.toFixed(2) }}s</div>
        </q-card-section>
        <q-separator />
        <q-card-section>
          <div v-if="summary">{{ summary }}</div>
          <div v-else class="text-grey">No summary available.</div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Close" color="primary" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { QPage, QForm, QInput, QBtn, QCard, QCardSection, QSeparator, QList, QItem, QItemSection, QSelect, QCheckbox } from 'quasar'
import type { SearchRequest, SearchResponse, SummaryResponse, TextChunkWithDocument, TagData } from 'src/models'
import { api } from 'src/boot/axios'

const searchForm = ref<SearchRequest>({
  query: '',
  limit: 10,
  type: 'hybrid', // Added the required 'type' property
  min_year: null,
  max_year: null,
  min_date: null,
  max_date: null,
  language: null
})

const loading = ref(false)
const results = ref<TextChunkWithDocument[]>([])
const timeSpent = ref(0)
const searchLog = ref<string[]>([])
const lastSearchRequest = ref<SearchRequest | null>(null)

const summaryType = ref('short')
const summaryTypes = [
  { label: 'Short', value: 'short' },
  { label: 'Detailed', value: 'detailed' }
]
const summarizing = ref(false)
const summary = ref('')
const summaryTimeSpent = ref(0)
const showSummary = ref(false)
const selectedResults = ref<Array<string | number>>([])
const summaries = ref<Array<{ summary: string, timeSpent: number, question?: string }>>([])
const questionInput = ref('')
const asking = ref(false)

const allSelected = computed(() => selectedResults.value.length === results.value.length && results.value.length > 0)

const tagFormManage = ref<TagData>({ tag_uuids: [''] })
const tagsLen = ref(5)
const tags = ref<TagData[]>([])
const loadingSpinner = ref(false)
const tagFilterModes = ref({
  positive: true, // by default check
  automatic: true
})

const tagMap = computed(() => {
  const map = new Map<string, TagData>()
  tags.value.forEach(t => map.set(t.tag_uuid, t))
  return map
})

async function onSearch () {
  loading.value = true
  results.value = []
  summary.value = ''
  summaries.value = [] // clear summaries and answered questions on new search
  try {
    console.log("Search will start")
    const { data } = await api.post<SearchResponse>('/search', searchForm.value)
    console.log("Search response received:", data)
    results.value = data.results
    timeSpent.value = data.time_spent
    searchLog.value = data.search_log
    lastSearchRequest.value = data.search_request
  } catch (e) {
    // handle error (could use Quasar Notify)
    results.value = []
    timeSpent.value = 0
    searchLog.value = []
    lastSearchRequest.value = null
  } finally {
    loading.value = false
  }
}

async function onSummarize () {
  if (!results.value.length || !lastSearchRequest.value) return
  summarizing.value = true
  // Use only selected results if any, otherwise all
  let toSummarize: TextChunkWithDocument[]
  if (selectedResults.value.length > 0) {
    const selectedSet = new Set(selectedResults.value)
    toSummarize = results.value.filter(r => selectedSet.has(r.id))
  } else {
    toSummarize = results.value
  }
  try {
    const payload = {
      results: toSummarize,
      search_request: lastSearchRequest.value,
      time_spent: timeSpent.value,
      search_log: searchLog.value
    }
    const { data } = await api.post<SummaryResponse>(`/summarize/${summaryType.value}`, payload)
    summaries.value.push({ summary: data.summary, timeSpent: data.time_spent })
  } catch (e) {
    summaries.value.push({ summary: 'Failed to summarize.', timeSpent: 0 })
  } finally {
    summarizing.value = false
  }
}

async function onAskQuestion () {
  if (!results.value.length || !lastSearchRequest.value || !questionInput.value.trim()) return
  asking.value = true
  const question = questionInput.value.trim()
  questionInput.value = ''
  // Use only selected results if any, otherwise all
  let toSend: TextChunkWithDocument[]
  if (selectedResults.value.length > 0) {
    const selectedSet = new Set(selectedResults.value)
    toSend = results.value.filter(r => selectedSet.has(r.id))
  } else {
    toSend = results.value
  }
  try {
    const payload = {
      results: toSend,
      search_request: lastSearchRequest.value,
      time_spent: timeSpent.value,
      search_log: searchLog.value
    }
    const { data } = await api.post<SummaryResponse>(`/question/${encodeURIComponent(question)}`, payload)
    summaries.value.push({ summary: data.summary, timeSpent: data.time_spent, question })
  } catch (e) {
    summaries.value.push({ summary: 'Failed to answer question.', timeSpent: 0, question })
  } finally {
    asking.value = false
  }
}

function toggleSelectAll () {
  if (allSelected.value) {
    selectedResults.value = []
  } else {
    selectedResults.value = results.value.map(r => r.id)
  }
}

// fetch tag info
async function fetchTags () {
  loadingSpinner.value = true
  try {
    const res = await api.get('/all_tags')
    tags.value = res.data.tags_lst
    tagsLen.value = tags.value.length
  } finally {
    loadingSpinner.value = false
  }
}

// filter search results by selected tags
async function onFilterByTag () {
  console.log("Filter")
  // results chunk.id
  // tagFormManage.tag_uuids
  // get all the found chunk ids from the search
  const chunkIds = results.value.map(c => c.id)
  const payload = {
    chunkIds: chunkIds,
    tagIds: tagFormManage.value.tag_uuids,
    positive: tagFilterModes.value.positive,
    automatic: tagFilterModes.value.automatic
  }
  const { data } = await api.post('/filter_tags', payload)
  // filter the current results
  const chunkTags = data?.chunkTags || []
  // Map chunk_id -> tag info from backend
  const chunkTagMap = new Map(
    chunkTags.map(c => [c.chunk_id, c])
  )

  // filter and enrich results
  results.value = (results.value || [])
    .filter(c => {
      const tagInfo = chunkTagMap.get(c.id)
      return tagInfo && (
        ((tagInfo.positive_tags_ids?.length || 0) > 0 && tagFilterModes.value.positive) ||
        ((tagInfo.automatic_tags_ids?.length || 0) > 0 && tagFilterModes.value.automatic)
      )
    })
    .map(c => {
      const chunkInfo = chunkTags.find(ct => ct.chunk_id === c.id) || {}
      return {
        ...c,
        positiveTags: (chunkInfo.positive_tags_ids || []).map(id => tagMap.value.get(id)).filter(Boolean),
        automaticTags: (chunkInfo.automatic_tags_ids || []).map(id => tagMap.value.get(id)).filter(Boolean)
      }
    })
  // results.value = (results.value || []).filter(c => filteredChunkIDs.has(c.id))
}

// add examples field
const addTag = () => {
  tagFormManage.value.tag_uuids.push('')
}

// remove examples field
const removeTag = (index: number) => {
  if (tagFormManage.value.tag_uuids.length > 1) {
    tagFormManage.value.tag_uuids.splice(index, 1)
  }
}
</script>
