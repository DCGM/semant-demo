<template>
  <q-dialog ref="dialogRef" @hide="onDialogHide" persistent>
    <q-card class="span-discussion-card column">
      <!-- Header -->
      <q-card-section class="row items-start no-wrap q-gutter-sm">
        <q-icon name="smart_toy" size="md" color="info" class="q-mt-xs" />
        <div class="col">
          <div class="text-h6 q-mb-xs">Discuss with AI</div>
          <div v-if="props.tagName" class="row items-center q-gutter-xs">
            <span
              v-if="props.tagColor"
              class="tag-dot"
              :style="{ backgroundColor: props.tagColor }"
            />
            <span class="text-subtitle2 text-grey-8">{{ props.tagName }}</span>
          </div>
          <div v-if="props.spanText" class="span-quote text-body2 q-mt-xs">
            &ldquo;{{ props.spanText }}&rdquo;
          </div>
        </div>
        <q-btn flat round dense icon="close" @click="onDialogCancel" />
      </q-card-section>

      <q-separator />

      <!-- Conversation -->
      <q-card-section ref="scrollContainer" class="conversation col">
        <div v-if="messages.length === 0 && !isStreaming" class="empty-state">
          <div class="text-grey-7 q-py-sm text-center">
            Ask the assistant whether this span fits the tag, or pick one of
            the suggestions below.
          </div>
        </div>
        <div
          v-for="(m, i) in messages"
          :key="i"
          class="msg-row"
          :class="m.role === 'user' ? 'msg-user' : 'msg-assistant'"
        >
          <div class="msg-bubble">
            <div class="msg-role">{{ m.role === 'user' ? 'You' : 'Assistant' }}</div>
            <div class="msg-content">{{ m.content }}<span v-if="isStreaming && i === messages.length - 1 && m.role === 'assistant'" class="cursor">▍</span></div>
          </div>
        </div>
        <q-banner v-if="error" dense class="bg-red-1 text-negative q-mt-sm">
          {{ error }}
        </q-banner>
      </q-card-section>

      <q-separator />

      <!-- Suggested prompts (shown when conversation is idle: empty or just
           after an assistant reply). -->
      <q-card-section v-if="showSuggestions" class="suggestions-section">
        <div class="suggestions">
          <q-btn
            v-for="(s, i) in SUGGESTED_PROMPTS"
            :key="i"
            no-caps
            outline
            color="primary"
            class="suggestion-btn"
            :icon="s.icon"
            :label="s.label"
            @click="onSuggestionClick(s.prompt)"
          />
        </div>
      </q-card-section>

      <q-separator />

      <!-- Input -->
      <q-card-section>
        <q-input
          v-model="draft"
          outlined
          dense
          autofocus
          autogrow
          placeholder="Ask about this span..."
          :disable="isStreaming"
          @keydown.enter.exact.prevent="onSubmit"
          @keydown.enter.shift.exact.stop
        >
          <template #after>
            <q-btn
              v-if="!isStreaming"
              unelevated
              color="primary"
              icon="send"
              :disable="!draft.trim()"
              @click="onSubmit"
            >
              <q-tooltip>Send (Enter)</q-tooltip>
            </q-btn>
            <q-btn
              v-else
              unelevated
              color="negative"
              icon="stop"
              @click="cancel"
            >
              <q-tooltip>Stop generating</q-tooltip>
            </q-btn>
          </template>
        </q-input>
        <div class="text-caption text-grey-7 q-mt-xs">
          Enter to send · Shift+Enter for newline
        </div>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useDialogPluginComponent } from 'quasar'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import useSpanDiscussion from 'src/composables/useSpanDiscussion'
import type { SpanDiscussionDialogProps } from './SpanDiscussionDialogTypes'

const props = defineProps<SpanDiscussionDialogProps>()
const { dialogRef, onDialogHide, onDialogCancel } = useDialogPluginComponent()
defineEmits([...useDialogPluginComponent.emits])

const { messages, isStreaming, error, send, cancel, reset } = useSpanDiscussion()
const draft = ref('')
const scrollContainer = ref<HTMLElement | null>(null)

// Quick-start prompts shown when the conversation is empty. They are sent
// verbatim as user messages — the model receives the full span / tag /
// document context anyway via the system instructions.
const SUGGESTED_PROMPTS: { icon: string; label: string; prompt: string }[] = [
  {
    icon: 'help_outline',
    label: 'Does this tag fit the highlighted text?',
    prompt: 'Does this tag fit the highlighted text? Explain why or why not.'
  },
  {
    icon: 'thumb_up',
    label: 'Arguments FOR this tagging',
    prompt: 'Give arguments for why this span SHOULD be labelled with this tag.'
  },
  {
    icon: 'thumb_down',
    label: 'Arguments AGAINST this tagging',
    prompt: 'Give arguments for why this span SHOULD NOT be labelled with this tag.'
  },
  {
    icon: 'balance',
    label: 'Summarise pros and cons',
    prompt: 'In a single answer, summarise the arguments for and against tagging this span and recommend whether to keep or remove it.'
  },
  {
    icon: 'travel_explore',
    label: 'Explain the wider context',
    prompt: 'Explain the wider context around the highlighted text — what is happening in the surrounding passage and how it relates to this span.'
  },
  {
    icon: 'menu_book',
    label: 'What is this text about?',
    prompt: 'Explain what the surrounding text is actually about. I do not understand it.'
  }
]

onMounted(() => {
  reset({ spanId: props.spanId, collectionId: props.collectionId })
})

onBeforeUnmount(() => {
  cancel()
})

const scrollToBottom = () => {
  void nextTick(() => {
    const el = (scrollContainer.value as unknown as { $el?: HTMLElement })?.$el ??
      (scrollContainer.value as HTMLElement | null)
    if (el) el.scrollTop = el.scrollHeight
  })
}

watch(messages, scrollToBottom, { deep: true })

const onSubmit = async () => {
  const text = draft.value.trim()
  if (!text || isStreaming.value) return
  draft.value = ''
  await send(text)
}

const onSuggestionClick = async (prompt: string) => {
  if (isStreaming.value) return
  await send(prompt)
}

// Show the suggested-prompt strip whenever the user can send a message and
// either the chat is empty or the assistant just finished its turn.
const showSuggestions = computed(() => {
  if (isStreaming.value) return false
  if (messages.value.length === 0) return true
  return messages.value[messages.value.length - 1]?.role === 'assistant'
})
</script>

<style scoped>
.span-discussion-card {
  width: 720px;
  max-width: 95vw;
  height: 80vh;
  max-height: 80vh;
}

.tag-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.span-quote {
  font-style: italic;
  color: #555;
  background: #fafafa;
  padding: 6px 10px;
  border-radius: 6px;
  border-left: 3px solid #1976d2;
  white-space: normal;
  word-break: break-word;
  max-height: 8em;
  overflow-y: auto;
}

.conversation {
  overflow-y: auto;
  background: #fcfcfc;
}

.empty-state {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.suggestions-section {
  padding-top: 10px;
  padding-bottom: 6px;
  background: #fafafa;
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.suggestion-btn {
  white-space: normal;
  line-height: 1.25;
  text-transform: none;
  font-size: 13px;
  padding: 6px 12px;
}

.suggestion-btn :deep(.q-btn__content) {
  justify-content: flex-start;
  text-align: left;
}

.msg-row {
  display: flex;
  margin-bottom: 10px;
}

.msg-user {
  justify-content: flex-end;
}

.msg-assistant {
  justify-content: flex-start;
}

.msg-bubble {
  max-width: 85%;
  padding: 8px 12px;
  border-radius: 10px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.45;
}

.msg-user .msg-bubble {
  background: #e3f2fd;
  color: #0d47a1;
  border-bottom-right-radius: 2px;
}

.msg-assistant .msg-bubble {
  background: #f1f3f4;
  color: #212121;
  border-bottom-left-radius: 2px;
}

.msg-role {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.4px;
  opacity: 0.6;
  text-transform: uppercase;
  margin-bottom: 2px;
}

.cursor {
  display: inline-block;
  margin-left: 2px;
  animation: blink 1s steps(2, start) infinite;
}

@keyframes blink {
  to { visibility: hidden; }
}
</style>
