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
            <div class="text-h6">{{ index + 1 }}. {{ chunk.title }}</div>
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
import type { SearchRequest, SearchResponse, SummaryResponse, TextChunkWithDocument } from 'src/models'
import { api } from 'src/boot/axios'

const searchForm = ref<SearchRequest>({
  query: '',
  limit: 10,
  type: 'text', // Added the required 'type' property
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

async function onSearch () {
  loading.value = true
  results.value = []
  summary.value = ''
  summaries.value = [] // clear summaries and answered questions on new search
  try {
    const { data } = await api.post<SearchResponse>('/search', searchForm.value)
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
    summaries.value.unshift({ summary: data.summary, timeSpent: data.time_spent })
  } catch (e) {
    summaries.value.unshift({ summary: 'Failed to summarize.', timeSpent: 0 })
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
    summaries.value.unshift({ summary: data.summary, timeSpent: data.time_spent, question })
  } catch (e) {
    summaries.value.unshift({ summary: 'Failed to answer question.', timeSpent: 0, question })
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
</script>
