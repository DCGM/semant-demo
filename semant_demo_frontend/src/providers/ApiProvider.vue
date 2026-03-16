<script setup lang="ts">
import { provide } from 'vue'
import { ApiClientInjectionKey, type ApiClients } from 'src/composables/useApi'
import { Configuration, DefaultApi } from 'src/generated/api'

const config = new Configuration({
  basePath: 'http://localhost:8000'
})

const apiClients: ApiClients = {
  default: new DefaultApi(config)
}

provide(ApiClientInjectionKey, apiClients)
</script>

<template>
  <slot />
</template>
