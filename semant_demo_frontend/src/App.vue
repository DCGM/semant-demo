<template>
  <router-view />
</template>

<script setup lang="ts">
import { useSessionScope } from 'src/app/session'
import { useQuotaScope } from 'src/features/quota/useQuotaScope'

useSessionScope()
useQuotaScope()
</script>
