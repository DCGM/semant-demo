import { boot } from 'quasar/wrappers'
import { Configuration, DefaultApi } from 'src/generated/api'
import { ApiClientInjectionKey, type ApiClients } from 'src/composables/useApi'

export default boot(({ app }) => {
  const basePath = process.env.BACKEND_URL || 'http://pcvaskom.fit.vutbr.cz:8024'

  const config = new Configuration({
    basePath,
    accessToken: () => {
      const token = localStorage.getItem('auth_token')
      return token ? `Bearer ${token}` : ''
    }
  })

  const apiClients: ApiClients = {
    default: new DefaultApi(config)
  }

  app.provide(ApiClientInjectionKey, apiClients)
})
