<template>
  <q-page padding>
    <div class="full-height flex column no-wrap"></div>
      <div class="q-pa-md flex-1 overflow-auto" ref="chatArea">
        <!-- bool while waiting for response --- 3 dots -->
        <q-chat-message v-if="isAiThinking" name="AI" bg-color="grey-2">
          <q-spinner-dots size="2em" />
        </q-chat-message>

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
            <div v-if="message.sender === 'AI'" v-html="message.text.replace(/\n/g, '<br>')"></div>
            <div v-else>{{ message.text }}</div>

            <!-- show sources -->
            <div v-if="message.sender === 'AI' && message.sources && message.sources.length > 0" class="q-mt-sm">
              <a href="#" @click.prevent="openSourcesDialog(message.sources)" class="source-link">Zdroje</a>
            </div>
          </template>
        </q-chat-message>
      </div>

      <q-dialog v-model="showSourcesDialog">
        <q-card style="width: 700px; max-width: 80vw;">
          <q-card-section>
            <div class="text-h6">Sources</div>
          </q-card-section>

          <q-card-section class="q-pt-none">
            <q-list bordered separator>
              <q-item v-for="(source, index) in currentSources" :key="index">
                <q-item-section>
                  <q-item-label overline>Source: {{ index + 1 }}</q-item-label>
                  <q-item-label caption>{{ source.text }}</q-item-label>
                </q-item-section>
              </q-item>
            </q-list>
          </q-card-section>

          <q-card-actions align="right">
            <q-btn flat label="Close" color="primary" v-close-popup />
          </q-card-actions>
        </q-card>
      </q-dialog>

      <!-- question input box -->
      <div class="q-pa-md bg-white input-area">
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
  </q-page>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import axios from 'axios'

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

// ---------------------------------------------------

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
    // search chunks
    const searchRequest = {
      query: userQuery,
      limit: 5,
      search_title_generate: false,
      search_summary_generate: false
    }
    const searchResponse = await axios.post('/api/search', searchRequest)
    if (!searchResponse.data || searchResponse.data.results.length === 0) {
      messages.value.push({ sender: 'AI', text: 'Sorry, we have no information about this topic.' })
      return
    }

    // rag question
    const ragRequestBody = {
      search_response: searchResponse.data,
      question: userQuery
    }
    const ragResponse = await axios.post('/api/rag', ragRequestBody)
    const ragAnswer = ragResponse.data.rag_answer

    // sources
    const sourcesForAnswer: Source[] = searchResponse.data.results.map((res: SearchResult) => ({
      text: res.text
    }))

    messages.value.push({
      sender: 'AI',
      text: ragAnswer,
      sources: sourcesForAnswer
    })
  } catch (error) {
    console.error('RAG error:', error)
    messages.value.push({ sender: 'AI', text: 'Sorry, error occurred while genereting response.' })
  } finally {
    isAiThinking.value = false
    scrollToBottom()
  }
}

// sources
const openSourcesDialog = (sources: Source[]) => {
  currentSources.value = sources
  showSourcesDialog.value = true
}

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
