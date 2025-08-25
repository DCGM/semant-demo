<template>
  <q-page class="flex column chat-container" style="padding: 0; margin: 0; padding-top: 52px;">
    <div class="q-pa-md flex-1 overflow-auto" ref="chatArea">
      <q-chat-message
        v-for="(message, index) in messages"
        :key="index"
        :name="message.sender"
        :text="[message.text]"
        :sent="message.sender === 'me'"
        :bg-color="message.sender === 'me' ? 'light-blue-2' : 'grey-2'"
        :text-color="message.sender === 'me' ? 'black' : 'black'"
        class="message-bubble"
      />
    </div>

    <div class="q-pa-md bg-white input-area">
      <q-form @submit.prevent="sendMessage">
        <q-input
          v-model="newMessage"
          placeholder="Napište zprávu..."
          outlined
          rounded
          dense
          class="q-px-md"
        >
          <template v-slot:append>
            <q-btn
              type="submit"
              icon="send"
              round
              dense
              flat
              color="primary"
            />
          </template>
        </q-input>
      </q-form>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const messages = ref([
  { sender: 'AI', text: 'Ahoj, co chceš?' },
  { sender: 'me', text: 'Ahoj, nevím.' },
  { sender: 'AI', text: 'Nice...' }
])

const newMessage = ref('')

const sendMessage = () => {
  if (newMessage.value.trim() === '') return

  messages.value.push({
    sender: 'me',
    text: newMessage.value.trim()
  })

  newMessage.value = ''
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
</style>
