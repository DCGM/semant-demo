import type { RouteLocationNormalized, Router, RouterScrollBehavior } from 'vue-router'

// Pages kept alive while another page is shown (#545): Search and Chat, so that a document
// opened from a result or a citation can be left again for the same results or conversation
// (MainLayout keeps the routes with `meta.keepAlive`). Their scroll position is kept with them:
// browser back restores it as for any page, and a link back to them (the document view's back
// link) finds it too. Every other page opens at the top.

declare module 'vue-router' {
  interface RouteMeta {
    /** The page is kept alive while other pages are shown (MainLayout). */
    keepAlive?: boolean
  }
}

export const isKept = (route: Pick<RouteLocationNormalized, 'meta'>) => route.meta.keepAlive === true

/** Remembers the scroll position of the kept pages left; returns the router's scroll behavior. */
export function keepScrollOfKeptPages (router: Router, scrollY: () => number = () => window.scrollY): RouterScrollBehavior {
  const positions = new Map<string, number>()
  router.beforeEach((_to, from) => {
    if (isKept(from) && typeof from.name === 'string') positions.set(from.name, scrollY())
  })
  return (to, _from, saved) => {
    if (saved) return saved
    const top = typeof to.name === 'string' && isKept(to) ? positions.get(to.name) : undefined
    return { left: 0, top: top ?? 0 }
  }
}
