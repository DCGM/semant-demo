import { inject, type InjectionKey } from 'vue'
import type { DefaultApi } from 'src/generated/api'

export interface ApiClients {
  default: DefaultApi
}

export const ApiKey: InjectionKey<ApiClients> = Symbol('ApiClients')

export function useApi(): ApiClients {
  const api = inject(ApiKey)

  if (!api) {
    throw new Error('useApi must be used within an ApiProvider')
  }

  return api
}
