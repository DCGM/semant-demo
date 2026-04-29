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
              @mouseup="handleMouseUp(index)"
              @click.capture="singleSourceClicks"
            ></div>
            <!-- show sources - bottom button  -->
            <div v-if="message.sender === 'AI' && message.sources && message.sources.length > 0" class="q-mt-sm">
              <a href="#" @click.prevent="openSourcesDialog(message.sources)" class="source-link">Sources</a>
            </div>
            <!-- like and dislike -->
            <div v-if="message.sender === 'AI' && index > 0" class="row items-center q-gutter-x-sm q-mt-xs">
              <q-btn
                flat round dense
                size="sm"
                icon="thumb_up"
                :color="message.userRating === 1 ? 'green' : 'grey'"
                :disable="message.userRating === 1"
                @click="handleFeedback(index, 1)"
              />
              <q-btn
                flat round dense
                size="sm"
                icon="thumb_down"
                :color="message.userRating === -1 ? 'red' : 'grey'"
                :disable="message.userRating === -1"
                @click="handleFeedback(index, -1)"
              />
            </div>
          </template>
        </q-chat-message>
      </div>
      <!-- dislike dialog  -->
      <q-dialog v-model="showFeedbackDialog">
        <q-card style="min-width: 400px">
          <q-card-section>
            <div class="text-subtitle1 text-weight-bold">Why didn't you like the answer? / Proč se Vám odpověď nelíbila?</div>
          </q-card-section>
          <q-card-section class="q-pt-none">
            <div class="text-caption q-mb-sm text-grey-8">Please select the type of error: / Vyberte prosím typ chyby:</div>
            <q-option-group
              v-model="selectedErrorTypes"
              :options="feedbackOptions"
              type="checkbox"
              color="primary"
          />
            <q-input v-model="feedbackComment" autogrow outlined label="Your comment (optional) / Váš komentář (nepovinné)" />
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Cancel / Zrušit" v-close-popup />
            <q-btn flat label="Send / Odeslat" color="primary" @click="submitFeedback" v-close-popup />
          </q-card-actions>
        </q-card>
      </q-dialog>

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
              style="min-width: 300px">
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

      <!-- explaination functionality -->
      <q-btn
      v-if="selectionData.show"
      ref="explainButttonnRef"
      label="Explain"
      color="primary"
      size="md"
      rounded
      dense
      unelevated
      class="absolute z-top shadow-10"
      :style="{ top: selectionData.y + 'px', left: selectionData.x + 'px', position: 'fixed' }"
      @click="explainSelection"
    />

    <q-dialog v-model="explanationDialog.show">
      <q-card style="width: 500px; max-width: 90vw;">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">Vysvětlení tvrzení</div>
          <q-space />
          <q-btn icon="close" flat round dense v-close-popup />
        </q-card-section>

        <q-card-section>
          <div class="text-italic q-mb-md">"{{ selectionData.text }}"</div>
          <q-separator q-mb-md />
          <div v-if="explanationDialog.loading" class="flex flex-center q-pa-lg">
            <q-spinner-dots size="2em" />
          </div>
          <div
            v-else
            v-html="convertToMarkdown(convertLinks(explanationDialog.text, messages[selectionData.msgIndex].sources, selectionData.msgIndex))"
            class="markdown-body"
            @click.capture="singleSourceClicks">
          </div>
        </q-card-section>
      </q-card>
    </q-dialog>

  </q-page>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import { marked } from 'marked'
import { useQuasar } from 'quasar'
const $q = useQuasar() // notifications
// ---------------------------------------------------
interface Source {
  text: string;
}

interface Message {
  sender: 'AI' | 'me';
  text: string;
  sources?: Source[];
  userRating?: number;
  response_id?: string;
}

interface RagRouteConfig {
  id: string
  name: string
  description: string
}

// First message from AI
const messages = ref<Message[]>([
  { sender: 'AI', text: 'Hello, what is your question? If you want to verify a statement, simply select it and click on the "Explain" button. / Ahoj, máte na mě nějakou otázku? Pokud chcete ověřit tvrzení, jednoduše jej vyberte a klikněte na tlačítko „Explain“.' }
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

const chunkNumber = ref<number>(5)

const explainButttonnRef = ref<any>(null)
const selectionData = ref({ show: false, x: 0, y: 0, text: '', msgIndex: -1 })
const explanationDialog = ref({ show: false, text: '', loading: false })

// message feedback
const showFeedbackDialog = ref(false)
const feedbackComment = ref('')
const currentFeedbackIndex = ref(-1)
const currentRating = ref(0)

const feedbackOptions = [
  { label: 'Factually incorrect / Fakticky nesprávné', value: 'fact_error' },
  { label: 'Irrelevant / Neodpovídá na otázku', value: 'not_relevant' },
  { label: 'Citation issues / Chybějící nebo špatné zdroje', value: 'citation_error' },
  { label: 'Wrong language or formatting / Chybný jazyk nebo formátování', value: 'language_issue' }
]
const selectedErrorTypes = ref([])

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
  document.addEventListener('mousedown', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', handleClickOutside)
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

  const lastAImessage = [...messages.value].reverse().find(m => m.sender === 'AI' && m.sources && m.sources.length > 0)
  const previousDocuments = lastAImessage ? lastAImessage.sources : []

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
      rag_search: ragSearch,
      previous_documents: previousDocuments
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
        sources: [],
        response_id: crypto.randomUUID()
      })
      return
    }
    // const sourcesForAnswer: Source[] = sources.map((res: SearchResult) => ({
    //   text: res.text
    // }))

    messages.value.push({
      sender: 'AI',
      text: ragAnswer,
      sources,
      response_id: ragResponse.data.response_id
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

// convert links
const convertLinks = (text: string, sources: Source[] | undefined, msgIndex: number) => {
  return text.replace(/\[([^[\]]+)\]/g, (match, content) => {
    return content.replace(/\b(?:doc|dokument)\s*(\d+)\b/gi, (docMatch, strIndex) => {
      const sourceIndex = parseInt(strIndex, 10) - 1 // -1 bcs array
      if (sources && sources[sourceIndex]) {
        return `<a href="#" class="source-link" data-message-index="${msgIndex}" data-source-index="${sourceIndex}">[doc ${strIndex}]</a>`
      }
      return docMatch
    })
  })
}

// Process source and conver to MarcDown
const replaceSourcesAndConvertToMarcdown = (msg: Message, msgIndex: number) => {
  if (msg.sender !== 'AI' || !msg.sources) { // replace sources only for AI messages
    return convertToMarkdown(msg.text)
  }
  const result = convertLinks(msg.text, msg.sources, msgIndex)
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
    { sender: 'AI', text: 'Hello, what is your question? If you want to verify a statement, simply select it and click on the "Explain" button. / Ahoj, máte na mě nějakou otázku? Pokud chcete ověřit tvrzení, jednoduše jej vyberte a klikněte na tlačítko „Explain“.' }
  ]
  newMessage.value = ''
  isAiThinking.value = false
}

// hide explain button if clicked elsewhere
const handleClickOutside = (event: MouseEvent) => {
  if (selectionData.value.show) {
    const buttonEl = explainButttonnRef.value?.$el
    if (buttonEl && !buttonEl.contains(event.target as Node)) {
      selectionData.value.show = false
    }
  }
}

// selection explain window
const handleMouseUp = (index: number) => {
  const selection = window.getSelection()
  const selectedText = selection ? selection.toString().trim() : ''

  if (selectedText.length > 5 && messages.value[index].sender === 'AI') {
    if (!selection || selection.rangeCount === 0) return
    const range = selection!.getRangeAt(0)
    const rect = range.getClientRects()
    const lastRect = rect[rect.length - 1]

    // get button location
    selectionData.value = {
      show: true,
      x: lastRect.right + 8,
      y: lastRect.bottom + 4,
      text: selectedText,
      msgIndex: index
    }
  } else {
    setTimeout(() => { selectionData.value.show = false }, 100)
  }
}

// selection window call backend
const explainSelection = async () => {
  const msgIndex = selectionData.value.msgIndex
  const aiMsg = messages.value[msgIndex]
  if (!aiMsg) return

  // get history
  const allRelevantMsg = messages.value.slice(0, msgIndex).filter(msg => msg.sources !== undefined) // remove messages without any informations

  // history for RAG
  const context = allRelevantMsg.map(msg => ({ role: msg.sender === 'me' ? 'user' : 'assistant', content: msg.text })) // convert to chatMessage format

  explanationDialog.value.show = true
  explanationDialog.value.loading = true
  explanationDialog.value.text = ''
  selectionData.value.show = false

  try {
    const response = await axios.post('/api/rag/explain', {
      rag_id: selectedRAG.value?.id,
      selected_text: selectionData.value.text,
      sources: aiMsg.sources,
      history: context,
      full_answer: aiMsg.text
    })
    explanationDialog.value.text = response.data.explanation
  } catch (error) {
    explanationDialog.value.text = 'Sorry, this part can not be explained.'
  } finally {
    explanationDialog.value.loading = false
  }
}

// messages feedback
const handleFeedback = (index: number, rating: number) => {
  currentFeedbackIndex.value = index
  currentRating.value = rating
  const msg = messages.value[index]

  if (msg.userRating === rating) return

  if (rating === -1) {
    feedbackComment.value = ''
    showFeedbackDialog.value = true
  } else {
    submitFeedback()
  }
}

const submitFeedback = async () => {
  const index = currentFeedbackIndex.value
  const msg = messages.value[index]
  const question = messages.value[index - 1]?.text || ''

  try {
    msg.userRating = currentRating.value
    await axios.post('/api/rag/feedback', {
      rag_id: selectedRAG.value?.id,
      response_id: msg.response_id,
      question,
      answer: msg.text,
      sources: msg.sources,
      rating: currentRating.value,
      comment: feedbackComment.value,
      error_types: selectedErrorTypes.value
    })

    // popup/alert window
    $q.notify({ color: 'positive', message: 'Thank you for your feedback. / Děkujeme za zpětnou vazbu.', icon: 'check' })
  } catch (e) {
    $q.notify({ color: 'negative', message: 'Error sending. / Chyba při odesílání.' })
  }
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
