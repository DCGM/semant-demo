<template>
  <q-btn
    v-if="quota.status && usedPercent !== null"
    flat
    dense
    no-caps
    class="quota-indicator q-mr-sm"
    icon="auto_awesome"
    :color="color"
    :label="$q.screen.gt.xs ? `${leftPercent}% AI left` : undefined"
    :aria-label="`AI allowance: ${leftPercent}% left today`"
  >
    <q-menu>
      <div class="q-pa-md quota-details" data-testid="quota-details">
        <div class="text-subtitle2">Today's AI allowance</div>
        <q-linear-progress
          class="q-my-sm"
          rounded
          size="8px"
          :value="usedPercent / 100"
          :color="color"
          aria-hidden="true"
        />
        <div>{{ usedPercent }}% used · {{ leftPercent }}% left</div>
        <div class="text-caption text-grey-8">Resets {{ reset }}.</div>
        <div class="text-caption text-grey-8 q-mt-sm">
          <template v-if="guest">
            Guest allowance of this browser. Logging in gives you a separate daily allowance.
          </template>
          <template v-else>Your account's allowance.</template>
        </div>
        <div class="text-caption text-grey-7 q-mt-xs">
          AI answers, chats and summaries use it, as an estimate of their processing cost;
          nothing is billed. Search and browsing do not use it.
        </div>
        <div v-if="guest" class="row q-gutter-sm q-mt-sm">
          <q-btn v-close-popup unelevated dense no-caps color="primary" label="Log in" @click="emit('login')" />
          <q-btn v-close-popup outline dense no-caps color="primary" label="Register" @click="emit('register')" />
        </div>
      </div>
    </q-menu>
  </q-btn>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { formatQuotaReset } from 'src/shared/api'
import { useQuotaStore } from './quotaStore'

// The header's view of the daily AI allowance (#234): share left, and in its menu the share
// used, the reset time and whose allowance it is. Percentages, not amounts: users are not billed.
const emit = defineEmits<{
  login: []
  register: []
}>()

const quota = useQuotaStore()
const { usedPercent, level, status } = storeToRefs(quota)

const leftPercent = computed(() => 100 - (usedPercent.value ?? 0))
const guest = computed(() => status.value?.principal === 'guest')
const reset = computed(() => status.value ? formatQuotaReset(status.value.resetAt) : '')
const color = computed(() => level.value === 'exhausted' ? 'negative' : level.value === 'near' ? 'orange-9' : 'grey-8')
</script>

<style scoped>
.quota-details {
  max-width: 300px;
}
</style>
