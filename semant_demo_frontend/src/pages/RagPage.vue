<template>
  <q-page padding>
    <div class="full-height flex column no-wrap"></div>
      <div class="q-pa-md flex-1 overflow-auto" ref="chatArea">
        <q-chat-message
          v-for="(message, index) in messages"
          :key="index"
          :name="message.sender"
          :sent="message.sender === 'me'"
          :bg-color="message.sender === 'me' ? 'light-blue-2' : 'grey-2'"
          :text-color="message.sender === 'me' ? 'black' : 'black'"
          class="message-bubble"
        >
          <template v-slot:default>
            <!-- message TEXT  -->
            <div
              v-html="replaceSourcesAndConvertToMarcdown(message, index)" class="markdown-body"
              @click.capture="singleSourceClicks"
            ></div>
            <!-- show sources - bottom button  -->
            <div v-if="message.sender === 'AI' && message.sources && message.sources.length > 0" class="q-mt-sm">
              <a href="#" @click.prevent="openSourcesDialog(message.sources)" class="source-link">Sources</a>
            </div>
          </template>
        </q-chat-message>
      </div>

      <!-- sources window -->
      <q-dialog v-model="showSourcesDialog">
        <q-card style="width: 700px; max-width: 80vw;">
          <q-card-section>
            <div class="text-h6">Sources</div>
          </q-card-section>

          <q-card-section class="q-pt-none">
            <q-list bordered separator>
              <q-item v-for="(source, index) in currentSources" :key="index">
                <q-item-section>
                  <!-- difference between one and more sources -->
                  <q-item-label overline>
                    <span v-if="currentSources.length > 1">Doc: {{ index + 1 }}</span>
                    <span v-else>Source of this information:</span>
                  </q-item-label>
                  <q-item-label caption>
                    <div v-html="convertToMarkdown(source.text)" class="markdown-body"></div>
                  </q-item-label>
                </q-item-section>
              </q-item>
            </q-list>
          </q-card-section>

          <q-card-actions align="right">
            <q-btn flat label="Close" color="primary" v-close-popup />
          </q-card-actions>
        </q-card>
      </q-dialog>
      <!-- bool while waiting for response --- 3 dots -->
      <q-chat-message v-if="isAiThinking" name="AI" bg-color="grey-2">
        <q-spinner-dots size="2em" />
      </q-chat-message>

      <!-- question input box -->
      <div class="q-pa-md bg-white input-area">
         <div class="row items-center no-wrap q-gutter-x-sm">
          <!-- reset chat button -->
          <q-btn
            icon="refresh"
            round
            flat
            @click="resetChat"
            class="q-mr-sm"
            title="Reset chat"
          />
            <q-select
              v-model="selectedRAG"
              :options="rags"
              option-label="name"
              label="RAG configuration"
              :loading="isLoadingRagConfigs"
              :disable="isLoadingRagConfigs || rags.length === 0"
              dense
              outlined
              style="min-width: 150px">
              <template v-slot:option="scope">
                <q-item v-bind="scope.itemProps">
                  <q-item-section>
                    <q-item-label>{{scope.opt.name }}</q-item-label>
                    <q-item-label caption lines="2">
                      {{ scope.opt.description }}
                    </q-item-label>
                  </q-item-section>
                </q-item>
              </template>
            </q-select>
          <!-- select model -->
            <!-- <q-select
              v-model="selectedModel"
              :options="models"
              label="Model"
              dense
              outlined
              style="width: 150px"
          /> -->
          <!-- temperature -->
            <!-- <span class="text-caption text-grey-7">Temperature:</span>
            <q-slider
              v-model="temperature"
              :min="tempRange.min"
              :max="tempRange.max"
              :step="0.1"
              label
              style="width: 100px"
          /> -->
          <!-- api key -->
          <!-- <q-input v-model="apiKey" label="Api key" dense outlined /> -->
          <!-- search mode -->
          <!-- <q-select
              v-model="selectedDBSearch"
              :options="searchModes"
              label="Search mode"
              dense
              outlined
              style="width: 150px"
          /> -->
          <!-- alpha -->
          <!-- <span class="text-caption text-grey-7">Alpha:</span>
          <q-slider
            v-model="alpha"
            :min="alphaRange.min"
            :max="alphaRange.max"
            :step="0.1"
            label
            style="width: 100px"
          /> -->
          <!-- <q-input v-model.number="chunkNumber" type="number" label="Chunk limit" dense outlined /> -->
          <q-input v-model="language" label="Language" dense outlined />
          <q-input v-model.number="minYear" type="number" label="Min Year" dense outlined />
          <q-input v-model.number="maxYear" type="number" label="Max Year" dense outlined />
        </div>
         <!-- input box with send button -->
        <div class="col">
          <q-input
            v-model="newMessage"
            placeholder="What is your question?"
            outlined
            rounded
            dense
            class="q-px-md"
            :disable="isAiThinking"
            @keyup.enter="sendMessage"
          >
            <template v-slot:append>
              <!-- Button call send directly - doesnt work with submit -->
              <q-btn
                icon="send"
                round
                dense
                flat
                color="primary"
                :loading="isAiThinking"
                @click="sendMessage"
              />
            </template>
          </q-input>
        </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import axios from 'axios'
import { marked } from 'marked'

// ---------------------------------------------------
interface Source {
  text: string;
}

interface SearchResult {
  text: string;
}

interface Message {
  sender: 'AI' | 'me';
  text: string;
  sources?: Source[];
}

interface RagRouteConfig {
  id: string
  name: string
  description: string
}

// First message from AI
const messages = ref<Message[]>([
  { sender: 'AI', text: 'Hello, what is your question?' }
])

const newMessage = ref('')
const chatArea = ref<HTMLElement | null>(null)
const isAiThinking = ref(false)

// sources dialog
const showSourcesDialog = ref(false)
const currentSources = ref<Source[]>([])

// selected rags from config
const rags = ref<RagRouteConfig[]>([])
const isLoadingRagConfigs = ref(true)
const selectedRAG = ref<RagRouteConfig | null>(null)

// models
const models = ref([
  { label: 'OLLAMA (local)', value: 'OLLAMA' },
  { label: 'GOOGLE (API)', value: 'GOOGLE' },
  { label: 'OPENAI (API)', value: 'OPENAI' }
])
const selectedModel = ref(models.value[0])

// temperature
// const temperature = ref(0.0)
// const tempRange = ref({ min: 0.0, max: 1.0 })

// api key
const apiKey = ref<string | null>(null)

// search modes
// const searchModes = ref([
//   { label: 'hybrid', value: 'hybrid' },
//   { label: 'vector', value: 'vector' },
//   { label: 'text', value: 'text' }
// ])
// const selectedDBSearch = ref(searchModes.value[0])

// alpha
// const alpha = ref(0.5)
// const alphaRange = ref({ min: 0.0, max: 1.0 })

const chunkNumber = ref<number>(5)
const minYear = ref<number | null>(null)
const maxYear = ref<number | null>(null)
const language = ref<string | null>(null)

// ----------------------Load RAGs----------------------

async function loadRagConfigs () {
  try {
    isLoadingRagConfigs.value = true
    const response = await axios.get('/api/rag/configurations')
    rags.value = response.data
    if (rags.value.length > 0) {
      selectedRAG.value = rags.value[0]
    }
  } catch (error) {
    messages.value.push({ sender: 'AI', text: 'None RAG model is avalaible.' })
  } finally {
    isLoadingRagConfigs.value = false
  }
}

onMounted(() => {
  loadRagConfigs()
})

// ----------------------Main chat-----------------------------

const scrollToBottom = () => {
  nextTick(() => {
    if (chatArea.value) {
      chatArea.value.scrollTop = chatArea.value.scrollHeight
    }
  })
}

const sendMessage = async () => {
  const userQuery = newMessage.value.trim()
  if (userQuery === '' || isAiThinking.value) return

  messages.value.push({ sender: 'me', text: userQuery })
  newMessage.value = ''
  scrollToBottom()

  // waiting
  isAiThinking.value = true

  try {
    // get history
    const allRelevantMsg = messages.value.slice(0, -1).filter(msg => msg.sources !== undefined || msg.sender === 'me') // remove messages without any informations

    // history for RAG
    const context = allRelevantMsg.map(msg => ({ role: msg.sender === 'me' ? 'user' : 'assistant', content: msg.text })) // convert to chatMessage format

    // const ragConfig = {
    //   model_type: selectedModel.value.value,
    //   temperature: 0.0, // temperature.value,
    //   api_key: apiKey.value ? apiKey.value : null
    // }
    const ragSearch = {
      search_query: userQuery, // is change in rag generator anyway (bcs it have to be refrased based on history context)
      limit: chunkNumber.value,
      search_type: 'hybrid', // selectedDBSearch.value.value,
      alpha: 0.5, // alpha.value, // vector search
      min_year: null, // minYear.value ? minYear.value : null, - does not work now
      max_year: null, // maxYear.value ? maxYear.value : null, - does not work now
      min_date: null,
      max_date: null,
      language: null // language.value ? language.value : null - does not work now
    }

    // rag question + search
    const ragRequestBody = {
      question: userQuery,
      history: context,
      // model configuration parameters
      // rag_config: ragConfig,
      // search parameters
      rag_search: ragSearch
    }
    const mainRagRequestBody = {
      rag_id: selectedRAG.value?.id,
      rag_request: ragRequestBody
    }
    const ragResponse = await axios.post('/api/rag', mainRagRequestBody)
    const ragAnswer = ragResponse.data.rag_answer
    const sources = ragResponse.data.sources

    // sources
    if (!sources || sources.length === 0) {
      messages.value.push({
        sender: 'AI',
        text: 'Sorry we have no information about this topick.',
        sources: []
      })
      return
    }
    const sourcesForAnswer: Source[] = sources.map((res: SearchResult) => ({
      text: res.text
    }))

    messages.value.push({
      sender: 'AI',
      text: ragAnswer,
      sources: sourcesForAnswer
    })
  } catch (error) {
    console.error('RAG error:', error)
    if (axios.isAxiosError(error) && error.response) {
      if (error.response.status === 401) {
        messages.value.push({ sender: 'AI', text: 'You have entered invalid API key.' })
      }
    } else {
      messages.value.push({ sender: 'AI', text: 'Sorry, error occurred while genereting response.' })
    }
  } finally {
    isAiThinking.value = false
    scrollToBottom()
  }
}

// ----------------------Other functions-----------------------------

// Markdown converter
const convertToMarkdown = (markdownText: string) => {
  if (!markdownText) return ''
  return marked(markdownText) as string
}

// Process source and conver to MarcDown

const replaceSourcesAndConvertToMarcdown = (msg: Message, msgIndex: number) => {
  if (msg.sender !== 'AI' || !msg.sources) { // replace sources only for AI messages
    return convertToMarkdown(msg.text)
  }

  const sourcesRegex = /\[doc\s*(\d+)\]/g

  // replace sources links
  const result = msg.text.replace(sourcesRegex, (match, strIndex) => {
    const sourceIndex = parseInt(strIndex, 10) - 1 // -1 bcs array
    if (msg.sources && msg.sources[sourceIndex]) {
      return `<a href="#" class="source-link" data-message-index="${msgIndex}" data-source-index="${sourceIndex}">[doc ${strIndex}]</a>`
    }
    return match // nothing found
  })
  return convertToMarkdown(result)
}

// sources
const openSourcesDialog = (sources: Source[]) => {
  currentSources.value = sources
  showSourcesDialog.value = true
}

const singleSourceClicks = (event: Event) => {
  const target = event.target as HTMLElement
  // check if element was clicked and have required atributes
  if (target.classList.contains('source-link') && target.dataset.sourceIndex && target.dataset.messageIndex) {
    event.preventDefault()
    // get indexes
    const msgIndex = parseInt(target.dataset.messageIndex, 10)
    const sourceIndex = parseInt(target.dataset.sourceIndex, 10)

    const clickedMsg = messages.value[msgIndex]

    if (clickedMsg && clickedMsg.sources && clickedMsg.sources[sourceIndex]) {
      openSourcesDialog([clickedMsg.sources[sourceIndex]])
    }
  }
}

// put chat into starting state
const resetChat = () => {
  messages.value = [
    { sender: 'AI', text: 'Hello, what is your question?' }
  ]
  newMessage.value = ''
  isAiThinking.value = false
}

// ----------------------Styles-----------------------------
</script>

<style scoped>
.chat-container {
  height: calc(100vh - 52px);
}

.message-bubble {
  max-width: 70%;
}

.input-area {
  border-top: 1px solid #e0e0e0;
}

.source-link {
  font-size: 0.8em;
  color: #027be3;
  text-decoration: none;
}

.source-link:hover {
  text-decoration: underline;
}
</style>
