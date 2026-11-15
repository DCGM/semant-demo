<template>
  <router-view />
</template>

<script setup lang="ts">
// CI probe for #687 stage 2 (throwaway, not to be merged)
import { useSessionScope } from 'src/app/session'
import { useQuotaScope } from 'src/features/quota/useQuotaScope'

useSessionScope()
useQuotaScope()
</script>
