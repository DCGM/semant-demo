import { QueryClient, type Query, type QueryKey } from '@tanstack/vue-query'

/**
 * Server-state cache (TanStack Vue Query, #630) for conventional reads. Requests still go
 * through the generated API client (`useApi`), so the token, credentials and 401 handling
 * stay in `shared/api`; a query only owns request identity (its key), deduplication,
 * loading/error state and invalidation. Query keys and composables live in their feature.
 *
 * Defaults are conservative, like the reads they replace: no retry (an expensive or
 * refused request is not repeated behind the user's back), no refetch on window focus or
 * reconnect, and no polling. Requests are always sent, also after the browser reported
 * being offline: the library would otherwise pause them, unsettled, until it reports a
 * connection again (a backend on localhost or the intranet may well be reachable), where a
 * failed request lets the page go on. A query that needs more says so itself, e.g. its
 * `staleTime`.
 */
export function createAppQueryClient (): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
        networkMode: 'always'
      },
      mutations: {
        networkMode: 'always'
      }
    }
  })
}

/** The application's one query client, registered by `boot/query.ts`. */
export const queryClient = createAppQueryClient()

/**
 * The `meta` of a query whose answer is the same for every user and every session
 * (configuration such as the search vectors): the only queries kept as they are at the
 * session boundary ({@link forgetUserQueries}).
 */
export const SHARED_QUERY = { shared: true } as const

/**
 * The key of a query whose answer depends on the signed-in user (their collections,
 * permissions, statistics), partitioned by the user's id so another user never reads it.
 * Build it from the current user reactively (a computed key), so a page that stays open
 * through a sign-out or an account switch asks under the new key instead of keeping the
 * dropped answer on screen.
 */
export function userScopedKey (userId: string, ...key: readonly unknown[]): QueryKey {
  return ['user', userId, ...key]
}

const isUserQuery = (query: Query): boolean => query.meta?.shared !== true

/**
 * Forgets what was loaded for the previous session (sign-in, sign-out, another user, also
 * from another tab; `useSessionScope`), for every query not marked {@link SHARED_QUERY}.
 * Safe by default: a query that forgets to say how it depends on the user is not served
 * to the next one.
 *
 * - A query nobody shows is dropped, with a request still under way (cancelled, its answer
 *   not kept).
 * - A query still shown (a kept-alive page, the layout; also one disabled meanwhile) is
 *   reset: its observers lose the old answer at once, and an enabled one is asked again
 *   under the new session. Dropping it would leave them showing the old answer, or loading
 *   forever when a request was cancelled.
 * - Finished mutations are dropped with their variables, answers and errors.
 */
export function forgetUserQueries (client: QueryClient = queryClient): void {
  client.removeQueries({ predicate: (query) => isUserQuery(query) && query.getObserversCount() === 0 })
  void client.resetQueries({ predicate: isUserQuery })
  client.getMutationCache().clear()
}
