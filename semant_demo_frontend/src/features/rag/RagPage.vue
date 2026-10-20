<template>
  <q-page padding>
    <div style="max-width: 900px; margin: 0 auto; width: 100%;">

      <div class="q-pa-md flex-1 overflow-auto" ref="chatArea">
        <q-chat-message
          v-for="(message, index) in messages"
          :key="message.id"
          :name="message.sender"
          :sent="message.sender === 'me'"
          :bg-color="message.sender === 'me' ? 'light-blue-2' : 'grey-2'"
          :text-color="message.sender === 'me' ? 'black' : 'black'"
          class="message-bubble"
        >
          <template v-slot:default>
            <div class="row items-center justify-between q-mt-sm q-pt-xs" style="border-top: 1px solid rgba(0,0,0,0.05)">
              <!-- message TEXT  -->
              <div
                v-html="replaceSourcesAndConvertToMarcdown(message)" class="markdown-body"
                @mouseup="handleMouseUp(index)"
                @click.capture="singleSourceClicks"
                @dblclick.capture="doubleSourceClicks"
              ></div>
              <!-- show sources - bottom button  -->
              <div v-if="message.sender === 'AI' && message.sources && message.sources.length > 0" class="row items-center justify-between q-mt-sm">
                <a href="#" class="source-link" @click.prevent="showSources(message)">Sources</a>
              </div>
              <!-- like and dislike -->
              <div v-if="message.sender === 'AI' && index > 0" class="row items-center q-gutter-x-xs">
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
            </div>
          </template>
        </q-chat-message>
      </div>

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
              placeholder="Vaše otázka?"
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
            ref="explanationEl"
            v-html="convertToMarkdown(convertLinks(explanationDialog.text, messages[selectionData.msgIndex]))"
            class="markdown-body"
            @click.capture="singleSourceClicks"
            @dblclick.capture="doubleSourceClicks">
          </div>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- All sources of the conversation, labelled as their citations (#246). -->
    <RightSidebarPanel v-if="chatSources.entries.value.length" :id="SOURCES_PANEL_ID" label="Sources" icon="format_quote">
      <ChatSourcesPanel
        :entries="chatSources.entries.value"
        :selected-id="chatSources.selectedId.value"
        :reveal="chatSources.reveal.value"
        @select="selectSource"
        @open="openSourceDocument"
      />
    </RightSidebarPanel>

    <!-- Registered once a source is opened in its document, so Sources stays the default panel. -->
    <RightSidebarPanel v-if="chatSources.documentSource.value" :id="CONTEXT_PANEL_ID" label="Document" icon="menu_book" :order="1">
      <ChunkContextPanel
        :target-chunk-id="sourceContext.target?.chunkId ?? null"
        :document="sourceContext.document"
        :chunks="sourceContext.chunks"
        :has-before="sourceContext.hasBefore"
        :has-after="sourceContext.hasAfter"
        :focus-request="sourceContext.focusRequest"
        :loading="sourceContext.loading"
        :extending="sourceContext.extending"
        :error="sourceContext.error"
        :target-label="chatSources.documentSource.value?.label ?? null"
        return-label="Return to cited passage"
        @extend="sourceContext.extend"
        @reload="sourceContext.load"
        @return="sourceContext.focus"
      />
    </RightSidebarPanel>
  </q-page>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted, onUpdated, watch } from 'vue'
import { marked } from 'marked'
import { useQuasar } from 'quasar'
import { SearchType, type RagChatMessage, type RagRouteConfig, type SearchResultChunk } from 'src/generated/api'
import { createContextGuard, errorStatus, quotaRefusalMessage, quotaRefusalOf, reportAiOperation, useApi } from 'src/shared/api'
import { useUserStore } from 'src/features/auth/userStore'
import RightSidebarPanel from 'src/app/sidebar/RightSidebarPanel.vue'
import { useRightSidebarStore } from 'src/app/sidebar/rightSidebarStore'
import ChunkContextPanel from 'src/features/documents/ChunkContextPanel.vue'
import ChatSourcesPanel from './ChatSourcesPanel.vue'
import { citedChunkId, useChatSources } from './useChatSources'
const $q = useQuasar() // notifications
const api = useApi().default
// ---------------------------------------------------
type Source = SearchResultChunk

interface Message {
  /** Stays the same for the message's lifetime; citations and the shown sources refer to it. */
  id: number;
  sender: 'AI' | 'me';
  text: string;
  sources?: Source[];
  userRating?: number;
  responseId?: string;
}

let lastMessageId = 0
const nextMessageId = () => ++lastMessageId

// First message from AI
const greeting = (): Message => ({
  id: nextMessageId(),
  sender: 'AI',
  text: 'Ahoj, máte na mě nějakou otázku?\n\n**Tip:** Označte část odpovědi a klikněte na **Explain** pro ověření tvrzení.'
})
const messages = ref<Message[]>([greeting()])

const newMessage = ref('')
const chatArea = ref<HTMLElement | null>(null)
const isAiThinking = ref(false)

// The conversation's sources, the selected one and one in its document, in the right sidebar
const SOURCES_PANEL_ID = 'chat-sources'
const CONTEXT_PANEL_ID = 'chat-source-context'
const rightSidebar = useRightSidebarStore()
const chatSources = useChatSources(messages)
const sourceContext = chatSources.context

// selected rags from config
const rags = ref<RagRouteConfig[]>([])
const isLoadingRagConfigs = ref(true)
const selectedRAG = ref<RagRouteConfig | null>(null)

const chunkNumber = ref<number>(5)

const explainButttonnRef = ref<{ $el: HTMLElement } | null>(null)
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
const selectedErrorTypes = ref<string[]>([])

// ----------------------Load RAGs----------------------

async function loadRagConfigs () {
  try {
    isLoadingRagConfigs.value = true
    rags.value = await api.getAvalaibleRagConfigurationsApiRagConfigurationsGet()
    if (rags.value.length > 0) {
      selectedRAG.value = rags.value[0]
    }
  } catch (error) {
    messages.value.push({ id: nextMessageId(), sender: 'AI', text: 'None RAG model is avalaible.' })
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

// The conversation: resetting it starts a new one, and answers (RAG, explanations) still
// on their way for the old one are dropped.
const conversation = createContextGuard()

// reset chat when change RAG configuration
watch(() => selectedRAG.value?.id, (_, oldId) => {
  if (oldId) {
    resetChat()
  }
})

// The questions and answers belong to whoever asked them: signing out, an expired session
// or another account (also from another tab) starts a new conversation. Signing in keeps
// a conversation started signed out.
const userStore = useUserStore()
watch(() => userStore.getUserId, (userId, previousUserId) => {
  if (previousUserId && userId !== previousUserId) resetChat()
})

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

  messages.value.push({ id: nextMessageId(), sender: 'me', text: userQuery })
  newMessage.value = ''
  scrollToBottom()

  // waiting
  isAiThinking.value = true
  const isCurrent = conversation.capture()

  try {
    // get history
    const allRelevantMsg = messages.value.slice(0, -1).filter(msg => msg.sources !== undefined || msg.sender === 'me') // remove messages without any informations

    // history for RAG
    const context = toChatHistory(allRelevantMsg)

    const ragResponse = await api.ragApiRagPost({
      ragRequestMain: {
        ragId: selectedRAG.value?.id ?? '',
        ragRequest: {
          question: userQuery,
          history: context,
          ragSearch: {
            searchQuery: userQuery, // is change in rag generator anyway (bcs it have to be refrased based on history context)
            limit: chunkNumber.value,
            searchType: SearchType.hybrid,
            alpha: 0.5, // vector search
            minYear: null, // year/date/language filters do not work now
            maxYear: null,
            minDate: null,
            maxDate: null,
            language: null
          },
          previousDocuments
        }
      }
    })
    if (!isCurrent()) return
    const ragAnswer = ragResponse.ragAnswer
    const sources = ragResponse.sources

    // sources
    if (!sources || sources.length === 0) {
      messages.value.push({
        id: nextMessageId(),
        sender: 'AI',
        text: 'Sorry we have no information about this topick.',
        sources: [],
        responseId: crypto.randomUUID()
      })
      return
    }
    // const sourcesForAnswer: Source[] = sources.map((res: SearchResult) => ({
    //   text: res.text
    // }))

    messages.value.push({
      id: nextMessageId(),
      sender: 'AI',
      text: ragAnswer,
      sources,
      responseId: ragResponse.responseId
    })
  } catch (error) {
    if (!isCurrent()) return
    console.error('RAG error:', error)
    // Refused for the daily AI allowance: nothing was generated and nothing is retried.
    const refusal = await quotaRefusalOf(error)
    if (!isCurrent()) return
    if (refusal) {
      messages.value.push({ id: nextMessageId(), sender: 'AI', text: quotaRefusalMessage(refusal) })
    } else if (errorStatus(error) === 401) {
      messages.value.push({ id: nextMessageId(), sender: 'AI', text: 'You have entered invalid API key.' })
    } else {
      messages.value.push({ id: nextMessageId(), sender: 'AI', text: 'Sorry, error occurred while genereting response.' })
    }
  } finally {
    reportAiOperation()
    if (isCurrent()) {
      isAiThinking.value = false
      scrollToBottom()
    }
  }
}

// ----------------------Other functions-----------------------------

// chat history for the RAG backend
const toChatHistory = (msgs: Message[]): RagChatMessage[] =>
  msgs.map(msg => ({ role: msg.sender === 'me' ? 'user' : 'assistant', content: msg.text }))

// Markdown converter
const convertToMarkdown = (markdownText: string) => {
  if (!markdownText) return ''
  return marked(markdownText) as string
}

// convert links: an answer's own citations `[doc N]` (or those of an explanation of it) become
// links labelled with the conversation-wide source label (`[S3]`). The text itself (history,
// explanation input) is not changed; a citation without a source of that answer stays as
// written. The HTML does not depend on the selection (markSelectedCitations), so selecting
// does not replace the clicked link and a double click still reaches it.
const escapeAttribute = (value: string) => value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')

const convertLinks = (text: string, msg: Message | undefined) => {
  return text.replace(/\[([^[\]]+)\]/g, (match, content: string) => {
    let linked = false
    const replaced = content.replace(/\b(?:doc|dokument)\s*(\d+)\b/gi, (docMatch: string, strIndex: string) => {
      const chunkId = citedChunkId(msg, parseInt(strIndex, 10))
      const label = chatSources.labelOf(chunkId)
      if (!chunkId || !label) return docMatch
      linked = true
      return `<a href="#" class="source-link" data-source-id="${escapeAttribute(chunkId)}">[${label}]</a>`
    })
    return linked ? replaced : match
  })
}

// Marks every citation of the selected source, in the conversation and the explanation.
const explanationEl = ref<HTMLElement | null>(null)
const markSelectedCitations = () => {
  const selected = chatSources.selectedId.value
  for (const root of [chatArea.value, explanationEl.value]) {
    root?.querySelectorAll<HTMLElement>('a.source-link[data-source-id]').forEach(link => {
      const isSelected = link.dataset.sourceId === selected
      link.classList.toggle('source-link--selected', isSelected)
      if (isSelected) link.setAttribute('aria-current', 'true')
      else link.removeAttribute('aria-current')
    })
  }
}
watch(() => chatSources.selectedId.value, markSelectedCitations, { flush: 'post' })
// Slot content (answers, the explanation) may re-render without the page.
watch([explanationEl, () => explanationDialog.value.text, () => messages.value.length], markSelectedCitations, { flush: 'post' })
onUpdated(markSelectedCitations)

// Process source and conver to MarcDown
const replaceSourcesAndConvertToMarcdown = (msg: Message) => {
  if (msg.sender !== 'AI' || !msg.sources) { // replace sources only for AI messages
    return convertToMarkdown(msg.text)
  }
  const result = convertLinks(msg.text, msg)
  return convertToMarkdown(result)
}

// Sources in the right sidebar. Selecting one never scrolls the conversation.
const selectSource = async (id: string) => {
  if (!chatSources.select(id)) return
  await nextTick() // the panel registers with the first answer's sources
  rightSidebar.activate(SOURCES_PANEL_ID)
}

const openSourceDocument = async (id: string) => {
  if (!chatSources.openDocument(id)) return
  await nextTick() // the panel registers when a source is opened for the first time
  rightSidebar.activate(CONTEXT_PANEL_ID)
}

// An answer's Sources link shows the list at its first source, without selecting it.
const showSources = async (msg: Message) => {
  const first = msg.sources?.[0]
  if (!first) return
  chatSources.revealSource(first.id)
  await nextTick()
  rightSidebar.activate(SOURCES_PANEL_ID)
}

const citedSourceId = (event: Event): string | null => {
  const target = event.target as HTMLElement
  if (!target.classList.contains('source-link') || !target.dataset.sourceId) return null
  event.preventDefault()
  // The modal explanation would cover the sidebar.
  explanationDialog.value.show = false
  return target.dataset.sourceId
}

// One click on a citation selects its source, a double click opens it in its document.
const singleSourceClicks = (event: Event) => {
  const id = citedSourceId(event)
  if (id) selectSource(id)
}

const doubleSourceClicks = (event: Event) => {
  const id = citedSourceId(event)
  if (id) openSourceDocument(id)
}

// put chat into starting state: no messages, sources, explanation or feedback of the old
// conversation stay open, and its pending answers are ignored
const resetChat = () => {
  conversation.enter()
  messages.value = [greeting()]
  newMessage.value = ''
  isAiThinking.value = false
  chatSources.clear()
  selectionData.value = { show: false, x: 0, y: 0, text: '', msgIndex: -1 }
  explanationDialog.value = { show: false, text: '', loading: false }
  showFeedbackDialog.value = false
  feedbackComment.value = ''
  selectedErrorTypes.value = []
  currentFeedbackIndex.value = -1
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
  const context = toChatHistory(allRelevantMsg)

  explanationDialog.value.show = true
  explanationDialog.value.loading = true
  explanationDialog.value.text = ''
  selectionData.value.show = false
  const isCurrent = conversation.capture()

  try {
    const response = await api.explainSelectionApiRagExplainPost({
      explainRequest: {
        ragId: selectedRAG.value?.id ?? '',
        selectedText: selectionData.value.text,
        sources: aiMsg.sources ?? [],
        history: context,
        fullAnswer: aiMsg.text
      }
    }) as { explanation?: string }
    if (isCurrent()) explanationDialog.value.text = response.explanation ?? ''
  } catch (error) {
    if (!isCurrent()) return
    // Refused for the daily AI allowance: say why and when it resets; nothing is retried.
    const refusal = await quotaRefusalOf(error)
    if (!isCurrent()) return
    explanationDialog.value.text = refusal ? quotaRefusalMessage(refusal) : 'Sorry, this part can not be explained.'
  } finally {
    reportAiOperation()
    if (isCurrent()) explanationDialog.value.loading = false
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
    await api.saveFeedbackApiRagFeedbackPost({
      feedbackRequest: {
        ragId: selectedRAG.value?.id ?? '',
        responseId: msg.responseId ?? '',
        question,
        answer: msg.text,
        sources: msg.sources ?? [],
        rating: currentRating.value,
        comment: feedbackComment.value,
        errorTypes: selectedErrorTypes.value
      }
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

.q-pa-md.flex-1.overflow-auto {
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
}

.message-bubble :deep(.q-chat-message-text) {
  padding: 8px 12px;
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

.markdown-body :deep(.source-link--selected) {
  font-weight: bold;
  background-color: #fff3b0;
  border-radius: 2px;
  outline: 1px solid var(--q-primary);
}

.markdown-body {
  word-wrap: break-word;
  font-size: 14px;
  line-height: 1.5;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 1.5rem !important;
  margin-top: 0.5rem;
  margin-bottom: 0.5rem;
  list-style-position: outside;
}

.markdown-body :deep(li) {
  margin-bottom: 4px;
}

.q-chat-message-text {
  max-width: 100%;
}
</style>
