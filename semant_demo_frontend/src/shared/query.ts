import { QueryClient, type QueryKey } from '@tanstack/vue-query'

/**
 * Server-state cache (TanStack Vue Query, #630) for conventional reads. Requests still go
 * through the generated API client (`useApi`), so the token, credentials and 401 handling
 * stay in `shared/api`; a query only owns request identity (its key), deduplication,
 * loading/error state and invalidation. Query keys and composables live in their feature.
 *
 * Defaults are conservative, like the reads they replace: no retry (an expensive or
 * refused request is not repeated behind the user's back), no refetch on window focus or
 * reconnect, and no polling. A query that needs more says so itself, e.g. its `staleTime`.
 */
export function createAppQueryClient (): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false
      }
    }
  })
}

/** The application's one query client, registered by `boot/query.ts`. */
export const queryClient = createAppQueryClient()

const USER_SCOPE = 'user'

/**
 * The key of a query whose answer depends on the signed-in user (their collections,
 * permissions, statistics): partitioned by the user's id, so another user never reads it,
 * and dropped by {@link forgetUserScopedQueries} at the session boundary. Reads that are
 * the same for everyone (configuration such as the search vectors) use a plain key.
 */
export function userScopedKey (userId: string, ...key: readonly unknown[]): QueryKey {
  return [USER_SCOPE, userId, ...key]
}

/**
 * Drops every user-scoped query (sign-out, another user, also from another tab;
 * `clearUserScopedState`): their cached answers, and requests still under way, whose
 * answers are then not kept. Queries with a plain key stay.
 */
export function forgetUserScopedQueries (client: QueryClient = queryClient): void {
  void client.cancelQueries({ queryKey: [USER_SCOPE] })
  client.removeQueries({ queryKey: [USER_SCOPE] })
}
