import { watch } from 'vue'
import type { RouteLocationNormalized, RouteLocationRaw, Router } from 'vue-router'
import type { useUserStore } from 'src/features/auth/userStore'

declare module 'vue-router' {
  interface RouteMeta {
    /** Only a signed-in user may open the route (and its children). */
    requiresAuth?: boolean
  }
}

/** Where a signed-out user goes instead of a route that needs a signed-in user. */
export const SIGNED_OUT_ROUTE: RouteLocationRaw = { name: 'search' }

export function requiresAuth (route: RouteLocationNormalized): boolean {
  return route.matched.some((record) => record.meta.requiresAuth)
}

/**
 * Keeps signed-out users off `requiresAuth` routes: a direct link waits for a stored
 * session to be restored, then opens the route or goes to {@link SIGNED_OUT_ROUTE}; signing
 * out (or an expired session) on such a route leaves it. `onDenied` tells a user sent away
 * from a direct link why; whoever ends a session reports that themselves.
 * The backend still authorizes every request; this only avoids showing pages that cannot work.
 */
export function installAuthGuard (
  router: Router,
  userStore: ReturnType<typeof useUserStore>,
  onDenied: () => void
): void {
  router.beforeEach(async (to) => {
    if (!requiresAuth(to)) return true
    await userStore.restoreSession()
    if (userStore.isLoggedIn) return true
    onDenied()
    return SIGNED_OUT_ROUTE
  })

  watch(() => userStore.isLoggedIn, (loggedIn, wasLoggedIn) => {
    if (loggedIn || !wasLoggedIn || !requiresAuth(router.currentRoute.value)) return
    void router.replace(SIGNED_OUT_ROUTE)
  })
}
