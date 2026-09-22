import { useApi } from 'src/composables/useApi'
import { UserSearchResult } from 'src/generated/api'

export function useUserRepository() {
  const api = useApi().default

  return {
    search: async (query: string): Promise<UserSearchResult[]> => {
      return api.searchUsersApiUsersSearchGet({ q: query })
    }
  }
}
