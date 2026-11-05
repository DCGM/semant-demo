<template>
  <!-- Whether the text keeps its original whitespace (spaces, line breaks) or collapses it;
       in the controls row of both document views (#600). -->
  <q-btn
    flat dense round
    icon="format_indent_increase"
    size="sm"
    class="whitespace-toggle"
    :class="{ 'whitespace-toggle--active': modelValue }"
    :aria-pressed="modelValue"
    aria-label="Original whitespace"
    :title="modelValue ? 'Switch to compact whitespace (collapse spaces & line breaks)' : 'Switch to original whitespace (preserve spaces & line breaks)'"
    data-testid="whitespace-toggle"
    @click="emit('update:modelValue', !modelValue)"
  >
    <q-tooltip v-if="modelValue">Showing original whitespace — click to collapse</q-tooltip>
    <q-tooltip v-else>Showing collapsed whitespace — click to preserve original</q-tooltip>
  </q-btn>
</template>

<script setup lang="ts">
defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
</script>

<style scoped>
.whitespace-toggle {
  color: #64748b;
  border-radius: 6px;
}

.whitespace-toggle--active {
  color: #1d4ed8;
  background: #eff6ff;
}
</style>
