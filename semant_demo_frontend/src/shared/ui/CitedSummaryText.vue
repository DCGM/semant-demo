<template>
  <div class="text-body2" style="white-space: pre-wrap;">
    <template v-for="(token, idx) in tokens" :key="idx">
      <span v-if="token.type === 'text'">{{ (token as TextToken).value }}</span>
      <a
        v-else
        href="#"
        class="citation-link"
        @click.prevent="emit('cite', token as Citation)"
      >[{{ label(token as Citation) }}]</a>
    </template>
  </div>
</template>

<script setup lang="ts" generic="Citation extends { type: 'citation' }">
import type { TextToken } from 'src/shared/citationTokens'

// Shared citation-rendering markup for an LLM summary's text/citation tokens (#358 review: the
// search-results and document summary panels had copy-pasted this `<a class="citation-link">`
// rendering and its CSS). `label`/`cite` stay generic over each caller's own citation token
// shape (search's number-only citations vs a document summary's chunk id + order).
type LabelFn = (citation: Citation) => string | number

defineProps<{
  tokens: Array<TextToken | Citation>
  label: LabelFn
}>()

const emit = defineEmits<{
  cite: [citation: Citation]
}>()
</script>

<style scoped>
.citation-link {
  color: var(--q-primary);
  text-decoration: underline;
}
</style>
