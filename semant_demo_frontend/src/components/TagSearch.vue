<template>
  <q-input
    ref="inputRef"
    v-model="searchText"
    dense
    outlined
    clearable
    placeholder="Search tags…"
    prepend-icon="search"
    class="tag-search-input"
  />
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { QInput } from 'quasar'

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{(e: 'update:modelValue', value: string): void}>()

const inputRef = ref<QInput | null>(null)

const searchText = computed({
  get: () => props.modelValue,
  set: (v: string) => emit('update:modelValue', v ?? '')
})

const focus = () => inputRef.value?.focus()

defineExpose({ focus })
</script>
