<template>
  <div class="column no-wrap scoped-chat-panel" data-testid="scoped-chat">
    <div class="row items-start no-wrap q-gutter-x-sm q-mb-sm">
      <div class="col text-caption text-grey-7" data-testid="chat-scope">{{ scopeLabel }}</div>
      <q-btn
        flat dense no-caps
        size="sm"
        class="new-conversation"
        icon="add_comment"
        label="New conversation"
        :disable="!messages.length"
        data-testid="chat-new-conversation"
        @click="emit('new-conversation')"
      />
    </div>

    <div
      v-if="scopeChanged && scopeChangedText"
      class="text-caption text-warning q-mb-sm"
      role="status"
      data-testid="chat-scope-changed"
    >
      <q-icon name="info" size="16px" class="q-mr-xs" />
      {{ scopeChangedText }}
    </div>

    <div ref="listRef" class="chat-messages col" role="log" aria-live="polite">
      <div v-if="!messages.length" class="text-caption text-grey-7">{{ emptyText }}</div>
      <template v-for="(message, index) in messages" :key="index">
        <div v-if="message.role === 'user'" class="chat-message chat-message--user q-mb-sm" data-testid="chat-question">
          {{ message.text }}
        </div>
        <div v-else class="chat-message chat-message--assistant q-mb-md" data-testid="chat-answer">
          <CitedSummaryText
            v-if="message.text"
            :tokens="chatTokens(message)"
            :label="(token) => `S${token.source.label}`"
            @cite="(token) => emit('cite', token.source)"
          />
          <div v-if="message.status === 'streaming'" class="row items-center q-gutter-xs text-grey-7 q-mt-xs">
            <q-spinner-dots size="1.2em" color="primary" />
          </div>
          <div
            v-if="message.coverage?.coverage === 'part'"
            class="text-caption text-warning q-mt-xs"
            role="status"
            data-testid="chat-coverage"
          >
            <q-icon name="warning" size="16px" class="q-mr-xs" />
            {{ coverageText(message.coverage) }}
          </div>
          <div v-if="message.status === 'stopped'" class="text-caption text-grey-7 q-mt-xs">Stopped.</div>
          <div v-if="message.error" class="text-negative text-body2 q-mt-xs" role="alert">{{ message.error }}</div>
        </div>
      </template>
    </div>

    <div v-if="summaryLength" class="row items-center no-wrap q-gutter-x-sm q-mt-sm" data-testid="chat-summary-controls">
      <q-btn
        outline no-caps
        color="secondary"
        icon="summarize"
        :label="summarizeLabel"
        :disable="streaming || disabled"
        data-testid="chat-summarize"
        @click="emit('summarize')"
      />
      <q-select
        :model-value="summaryLength"
        :options="SUMMARY_LENGTH_OPTIONS"
        label="Length"
        dense
        outlined
        emit-value
        map-options
        class="col"
        :disable="streaming"
        data-testid="chat-summary-length"
        @update:model-value="emit('update:summaryLength', $event)"
      />
    </div>

    <div class="row items-end no-wrap q-gutter-x-sm q-mt-sm">
      <q-input
        v-model="draft"
        class="col"
        type="textarea"
        autogrow
        dense
        outlined
        :maxlength="MAX_QUESTION_CHARS"
        :label="inputLabel"
        :input-style="{ maxHeight: '8em' }"
        data-testid="chat-input"
        @keydown.enter.exact="onEnter"
      />
      <q-btn
        v-if="streaming"
        round dense flat
        color="negative"
        icon="stop"
        aria-label="Stop the answer"
        data-testid="chat-stop"
        @click="emit('stop')"
      />
      <q-btn
        v-else
        round dense
        color="primary"
        icon="send"
        aria-label="Send the question"
        :disable="disabled || !draft.trim()"
        data-testid="chat-send"
        @click="send"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import CitedSummaryText from 'src/shared/ui/CitedSummaryText.vue'
import type { SummaryLength } from 'src/generated/api'
import { SUMMARY_LENGTH_OPTIONS } from 'src/shared/summaryLength'
import { chatTokens, MAX_QUESTION_CHARS, type ChatCoverage, type ChatMessage, type ChatSource } from './useScopedChat'

// Props-in/events-out only (docs/RIGHT_SIDEBAR.md section 3): the page owns
// useScopedChat() and its scope and passes the conversation here.
type CoverageText = (coverage: ChatCoverage) => string

// The wording defaults to the document scope (#248); other scopes pass their own.
const props = withDefaults(defineProps<{
  messages: ChatMessage[]
  streaming: boolean
  /** What the next question is about, e.g. "Asking about this document". */
  scopeLabel: string
  /** Nothing to ask about yet (e.g. search results still loading): the question cannot be sent. */
  disabled?: boolean
  /** The scope changed since the shown conversation (`useScopedChat().scopeChanged`). */
  scopeChanged?: boolean
  /** Shown while `scopeChanged`: what the next question, in a new conversation, is about. */
  scopeChangedText?: string
  emptyText?: string
  inputLabel?: string
  /** The note under an answer based on only a part of the scope. */
  coverageText?: CoverageText
  /** With a length, the panel offers *Summarize* (a summary of the scope as the next answer). */
  summaryLength?: SummaryLength | null
  summarizeLabel?: string
}>(), {
  summaryLength: null,
  summarizeLabel: 'Summarize',
  disabled: false,
  scopeChanged: false,
  scopeChangedText: '',
  emptyText: 'Ask a question about this document. Answers cite its passages as S1, S2…; click one to show it in the text.',
  inputLabel: 'Ask about this document',
  coverageText: (coverage: ChatCoverage) =>
    `Based on the first ${coverage.usedChunks} of ${coverage.totalChunks} passages of the document.`
})

const emit = defineEmits<{
  ask: [question: string]
  stop: []
  cite: [source: ChatSource]
  'new-conversation': []
  summarize: []
  'update:summaryLength': [value: SummaryLength]
}>()

const draft = ref('')
const listRef = ref<HTMLElement | null>(null)

function send () {
  const question = draft.value.trim()
  if (!question || props.streaming || props.disabled) return
  emit('ask', question)
  draft.value = ''
}

// Enter sends, Shift+Enter is a new line; Enter that confirms an IME composition only
// confirms it.
function onEnter (event: KeyboardEvent) {
  if (event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  send()
}

const NEAR_BOTTOM_PX = 40

// A new question scrolls to the end; a streaming answer is followed only while the list is
// at its end, so the user can scroll up and read earlier messages. (Runs before the DOM
// update, so the position measured is the one the user left.)
watch(() => {
  const last = props.messages[props.messages.length - 1]
  return [props.messages.length, last?.text.length ?? 0, last?.status ?? ''] as const
}, async ([count], [previousCount]) => {
  const list = listRef.value
  if (!list) return
  const atEnd = list.scrollHeight - list.scrollTop - list.clientHeight <= NEAR_BOTTOM_PX
  await nextTick()
  if (count !== previousCount || atEnd) list.scrollTop = list.scrollHeight
})
</script>

<style scoped>
.scoped-chat-panel {
  height: 100%;
  min-height: 0;
}

.new-conversation {
  flex: none;
}

.chat-messages {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
}

.chat-message {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.chat-message--user {
  align-self: flex-end;
  margin-left: 2em;
  padding: 6px 10px;
  border-radius: 8px;
  background: #e3ecf7;
}

.chat-message--assistant {
  padding: 2px 0;
}
</style>
