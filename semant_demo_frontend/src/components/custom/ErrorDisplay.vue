<template>
  <div v-if="error" class="q-mb-md text-h4 text-negative flex flex-center">
    <q-icon
      name="error"
      class="q-mr-sm"

    />
    {{ error }}
  </div>
</template>

<script setup lang="ts">

defineProps<{
  error: string | null;
}>()

</script>
