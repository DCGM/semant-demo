<script setup lang="ts">
import { provide } from 'vue'
import { ApiClientInjectionKey, type ApiClients } from 'src/composables/useApi'
import { Configuration, DefaultApi } from 'src/generated/api'

// Fallback provider: primary ApiClients injection now happens globally in src/boot/api-client.ts.
// Keep this component for easy rollback/experiments with component-scoped provide.

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
