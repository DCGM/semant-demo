<template>
  <!-- Nothing for a public document (#279). -->
  <q-badge
    v-if="rights !== 'public'"
    outline
    :color="rights === 'restricted' ? 'deep-orange-9' : 'grey-8'"
    class="document-rights"
    :data-rights="rights"
    data-testid="document-rights"
  >
    <q-icon :name="rights === 'restricted' ? 'lock' : 'help_outline'" size="12px" class="q-mr-xs" aria-hidden="true" />
    <span data-testid="document-rights-label">{{ RIGHTS_LABEL[rights] }}</span>
    <q-tooltip max-width="280px">{{ RIGHTS_HINT[rights] }}</q-tooltip>
  </q-badge>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { QBadge, QIcon, QTooltip } from 'quasar'
import { RIGHTS_HINT, RIGHTS_LABEL, documentRights } from './documentRights'

const props = defineProps<{
  /** `Document.public` (`_public` in the generated client). */
  value: boolean | null | undefined
}>()

const rights = computed(() => documentRights(props.value))
</script>

<style scoped>
.document-rights {
  vertical-align: middle;
  white-space: nowrap;
}
</style>
