import { inject, type InjectionKey } from 'vue'
import type { DefaultApi } from 'src/generated/api'

export interface ApiClients {
  default: DefaultApi
}

// provider injection key
export const ApiClientInjectionKey: InjectionKey<ApiClients> = Symbol('ApiClients')

export function useApi(): ApiClients {
  const api = inject(ApiClientInjectionKey)

  if (!api) {
    throw new Error('useApi must be used within an ApiProvider')
  }

  return api
}
