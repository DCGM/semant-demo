import { createContextGuard } from './context'

/**
 * The signed-in user's session as a context. `endSession()` (sign-out, another user)
 * makes every captured check false, so a request started under the old session (a read,
 * or a write the backend still completes) cannot put that user's data, errors or loading
 * state back into the cleared stores.
 */
const session = createContextGuard()

/** A check that stays true until the session ends. */
export function captureSession (): () => boolean {
  return session.capture()
}

export function endSession (): void {
  session.enter()
}
