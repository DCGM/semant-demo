/**
 * Identity of the context (collection, document, search, conversation...) that requests
 * belong to. A response may only change state while the context it was started for is
 * still current: cancellation alone is not enough, because a response can already be on
 * its way when the request is aborted.
 *
 *     const guard = createContextGuard()
 *     guard.enter()                  // new context: earlier responses become stale
 *     const isCurrent = guard.capture()
 *     const data = await fetchSomething()
 *     if (!isCurrent()) return       // a later context has started meanwhile
 */
export interface ContextGuard {
  /** Starts a new context; checks captured before now become false. */
  enter (): void
  /** A check that stays true until the next `enter()`. */
  capture (): () => boolean
}

export function createContextGuard (): ContextGuard {
  let token = 0
  return {
    enter () {
      token++
    },
    capture () {
      const captured = token
      return () => captured === token
    }
  }
}
