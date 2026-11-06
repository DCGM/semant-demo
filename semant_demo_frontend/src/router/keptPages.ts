import { reactive } from 'vue'
import type { LocationQuery, RouteLocationNormalized, RouteLocationRaw, Router, RouterScrollBehavior } from 'vue-router'

// Pages kept alive while another page is shown (#545): Search and Chat, so that a document
// opened from a result or a citation can be left again for the same results or conversation
// (MainLayout keeps the routes with `meta.keepAlive`). Their scroll position is kept with them:
// browser back restores it as for any page, and a link back to them (the document view's back
// link) finds it too. Every other page opens at the top.
//
// Their URL is kept with them too: Search keeps its applied criteria in its query (#605), so a
// link back to it (`keptLocation`: the drawer, the document view's back link) carries the query
// it was left with and finds the same search, instead of opening an empty one.

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

const lastQueries = reactive<Record<string, LocationQuery>>({})

/** Remembers the query each kept page was last shown with. */
export function rememberKeptLocations (router: Router): void {
  router.afterEach((to, _from, failure) => {
    if (!failure && isKept(to) && typeof to.name === 'string') lastQueries[to.name] = { ...to.query }
  })
}

/** A link to the kept page `name` as it was last shown (its query); reactive. */
export function keptLocation (name: string): RouteLocationRaw {
  return { name, query: lastQueries[name] ?? {} }
}

/** Forgets the remembered queries (tests). */
export function forgetKeptLocations (): void {
  for (const name of Object.keys(lastQueries)) delete lastQueries[name]
}
