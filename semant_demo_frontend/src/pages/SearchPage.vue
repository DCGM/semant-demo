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
          <q-input v-model="searchForm.min_year" type="number" label="Min Year" dense outlined />
        </div>
        <div class="col">
          <q-input v-model="searchForm.max_year" type="number" label="Max Year" dense outlined />
        </div>
        <div class="col-auto flex flex-center">
          <q-btn type="submit" color="primary" label="Search" :loading="loading" />
        </div>
      </div>
    </q-form>

    <div v-if="results.length" class="q-mt-lg">
      <q-card>
        <q-card-section>
          <div class="text-h6">Results ({{ results.length }})</div>
          <div class="text-caption text-grey">Time spent: {{ timeSpent.toFixed(2) }}s</div>
        </q-card-section>
        <q-separator />
        <q-card-section>
          <q-list bordered separator>
            <q-item v-for="chunk in results" :key="chunk.id">
              <q-item-section>
                <div class="text-bold">{{ chunk.title }}</div>
                <div class="text-caption">
                  {{ chunk.document_object.author || 'Unknown Author' }} | {{ chunk.document_object.yearIssued || 'Year N/A' }}
                </div>
                <div class="q-mt-xs">{{ chunk.text }}</div>
                <div class="text-caption text-grey">
                  Pages: {{ chunk.from_page }}-{{ chunk.to_page }}
                </div>
              </q-item-section>
            </q-item>
          </q-list>
        </q-card-section>
        <q-separator />
        <q-card-actions align="right">
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
            :disable="!results.length"
          />
        </q-card-actions>
      </q-card>
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
import { ref } from 'vue'
import { QPage, QForm, QInput, QBtn, QCard, QCardSection, QCardActions, QSeparator, QList, QItem, QItemSection, QDialog, QSelect } from 'quasar'
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

async function onSearch () {
  loading.value = true
  results.value = []
  summary.value = ''
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
  summary.value = ''
  try {
    const payload = {
      results: results.value,
      search_request: lastSearchRequest.value,
      time_spent: timeSpent.value,
      search_log: searchLog.value
    }
    const { data } = await api.post<SummaryResponse>(`/summarize/${summaryType.value}`, payload)
    summary.value = data.summary
    summaryTimeSpent.value = data.time_spent
    showSummary.value = true
  } catch (e) {
    summary.value = 'Failed to summarize.'
    summaryTimeSpent.value = 0
    showSummary.value = true
  } finally {
    summarizing.value = false
  }
}
</script>
