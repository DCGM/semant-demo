import { watch } from 'vue'
import type { RouteLocationNormalized, RouteLocationRaw, Router } from 'vue-router'
import type { useUserStore } from 'src/features/auth/userStore'
import { tokenSubject } from 'src/shared/api'

declare module 'vue-router' {
  interface RouteMeta {
    /** Only a signed-in user may open the route (and its children). */
    requiresAuth?: boolean
  }
}

/** Where a signed-out user goes instead of a route that needs a signed-in user. */
export const SIGNED_OUT_ROUTE: RouteLocationRaw = { name: 'search' }

/**
 * Where a protected route waits while the stored session cannot be verified (server
 * unreachable or failing). `redirect` keeps the requested route, opened once verified.
 */
export const SESSION_PENDING_ROUTE = 'sessionPending'

export function requiresAuth (route: RouteLocationNormalized): boolean {
  return route.matched.some((record) => record.meta.requiresAuth)
}

/** The route a pending protected link asked for: an in-app path only, never a URL. */
function pendingTarget (router: Router, route: RouteLocationNormalized): RouteLocationRaw {
  const redirect = route.query.redirect
  if (typeof redirect !== 'string' || !redirect.startsWith('/') || redirect.startsWith('//')) return SIGNED_OUT_ROUTE
  const target = router.resolve(redirect)
  if (!target.matched.length || target.name === SESSION_PENDING_ROUTE) return SIGNED_OUT_ROUTE
  return target.fullPath
}

/**
 * Keeps signed-out users off `requiresAuth` routes: a direct link waits for a stored
 * session to be restored, then opens the route or goes to {@link SIGNED_OUT_ROUTE}; signing
 * out (or an expired session) on such a route leaves it. `onDenied` tells a user sent away
 * from a direct link why; whoever ends a session reports that themselves.
 * A stored session that cannot be verified (server unreachable or failing) is not signed
 * out: a protected link waits on {@link SESSION_PENDING_ROUTE} and opens once the session
 * is verified (retry in the layout), or goes to search when the session ends there.
 * The backend still authorizes every request; this only avoids showing pages that cannot work.
 */
export function installAuthGuard (
  router: Router,
  userStore: ReturnType<typeof useUserStore>,
  onDenied: () => void
): void {
  // The account (token subject) the pending route waits for; its destination belongs to it.
  let pendingAccount: string | null = null
  const accountOf = (token: string) => tokenSubject(token) ?? token

  router.beforeEach(async (to) => {
    if (to.name === SESSION_PENDING_ROUTE) {
      await userStore.restoreSession()
      if (userStore.isLoggedIn) return pendingTarget(router, to)
      if (!userStore.restoreFailed || !userStore.token) return SIGNED_OUT_ROUTE
      pendingAccount = accountOf(userStore.token)
      return true
    }
    if (!requiresAuth(to)) return true
    await userStore.restoreSession()
    if (userStore.isLoggedIn) return true
    if (userStore.restoreFailed) return { name: SESSION_PENDING_ROUTE, query: { redirect: to.fullPath } }
    onDenied()
    return SIGNED_OUT_ROUTE
  })

  watch(() => userStore.isLoggedIn, (loggedIn, wasLoggedIn) => {
    if (loggedIn || !wasLoggedIn || !requiresAuth(router.currentRoute.value)) return
    void router.replace(SIGNED_OUT_ROUTE)
  })

  // The pending route resolves when the session is verified or ends (Sign out, 401, another
  // tab). Its destination belongs to the waiting account: another account's token drops it.
  watch(() => [userStore.isLoggedIn, userStore.token] as const, ([loggedIn, token]) => {
    const current = router.currentRoute.value
    if (current.name !== SESSION_PENDING_ROUTE) return
    if (!token || accountOf(token) !== pendingAccount) void router.replace(SIGNED_OUT_ROUTE)
    else if (loggedIn) void router.replace(pendingTarget(router, current))
  })
}
