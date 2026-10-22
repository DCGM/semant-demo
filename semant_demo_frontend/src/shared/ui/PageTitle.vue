<template>
  <div class="q-px-md">
    <span class="text-h4 text-weight-medium">
      {{ props.title }}
    </span>
  </div>
  <q-separator spaced inset />
</template>

<script setup lang="ts">
const props = defineProps<{
  title: string
}>()
</script>
