<template>
  <router-view />
</template>

<script setup lang="ts">
import { useSessionScope } from 'src/app/session'

useSessionScope()
</script>
