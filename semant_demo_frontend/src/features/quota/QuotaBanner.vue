<template>
  <q-banner
    v-if="visible"
    dense
    class="quota-banner text-grey-9"
    :class="exhausted ? 'bg-red-1' : 'bg-orange-1'"
    role="status"
    data-testid="quota-banner"
  >
    <template #avatar>
      <q-icon :name="exhausted ? 'block' : 'hourglass_bottom'" :color="exhausted ? 'negative' : 'orange-9'" />
    </template>
    {{ message }}
    <template #action>
      <template v-if="guest">
        <q-btn flat dense no-caps color="primary" label="Log in" @click="emit('login')" />
        <q-btn flat dense no-caps color="primary" label="Register" @click="emit('register')" />
      </template>
      <q-btn flat dense no-caps color="primary" label="Dismiss" @click="dismiss" />
    </template>
  </q-banner>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { formatQuotaReset } from 'src/shared/api'
import { useQuotaStore } from './quotaStore'

// A subtle warning once the near-limit share of the daily AI allowance is used, and a notice
// when it is used up (#234). Dismissing hides it until the level, principal or day changes.
// Guests are offered Log in / Register; signed-in users are not asked to register.
const emit = defineEmits<{
  login: []
  register: []
}>()

const quota = useQuotaStore()
const { status, level, usedPercent } = storeToRefs(quota)

const exhausted = computed(() => level.value === 'exhausted')
const guest = computed(() => status.value?.principal === 'guest')
const key = computed(() => status.value && level.value !== 'ok'
  ? `${status.value.principal}:${status.value.day}:${level.value}`
  : null)
const dismissed = ref<string | null>(null)
const visible = computed(() => key.value !== null && key.value !== dismissed.value)

const message = computed(() => {
  if (!status.value) return ''
  const reset = formatQuotaReset(status.value.resetAt)
  const login = guest.value ? ' Logging in gives you a separate daily allowance.' : ''
  return exhausted.value
    ? `Today's AI allowance is used up. AI answers, chats and summaries are available again ${reset}; search and browsing still work.${login}`
    : `You have used ${usedPercent.value}% of today's AI allowance. It resets ${reset}.${login}`
})

function dismiss () {
  dismissed.value = key.value
}
</script>
