<template>
  <div class="q-pl-xl">
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
