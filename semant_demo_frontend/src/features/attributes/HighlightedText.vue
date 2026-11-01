<template>
  <!-- The text with each match of the search marked (#506). -->
  <span><template v-for="(part, index) in parts" :key="index"><mark v-if="part.match" class="search-match">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { matchParts } from './attributeSearch'

const props = defineProps<{ text: string, needle?: string | null }>()
const parts = computed(() => matchParts(props.text, props.needle))
</script>

<style scoped>
.search-match {
  background: #ffe58a;
  color: inherit;
  border-radius: 2px;
  padding: 0;
}
</style>
