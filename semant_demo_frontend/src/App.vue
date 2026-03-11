<template>
  <ApiProvider>
    <router-view />
  </ApiProvider>
</template>

<script setup lang="ts">
import ApiProvider from './providers/ApiProvider.vue'
</script>
