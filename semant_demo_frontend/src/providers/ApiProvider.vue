<script setup lang="ts">
import { provide } from 'vue'
import { ApiClientInjectionKey, type ApiClients } from 'src/composables/useApi'
import { Configuration, DefaultApi } from 'src/generated/api'

const basePath = (process.env.BACKEND_URL || 'http://pcvaskom.fit.vutbr.cz:8024')

const config = new Configuration({
  basePath
})

const apiClients: ApiClients = {
  default: new DefaultApi(config)
}

provide(ApiClientInjectionKey, apiClients)
</script>

<template>
  <slot />
</template>
