import { BACKEND_URL } from './config'

const FRAME_ID = 'semant-download-frame'

/**
 * Hands a backend download (e.g. `/api/exports/collections/<ticket>`, a path that is its own
 * credential) to the browser's download manager, which saves it straight to disk with its
 * progress; nothing is held in memory. It loads in a hidden frame, so an error answer (an
 * expired link, access revoked meanwhile) never replaces the app page.
 */
export function startDownload (path: string): void {
  let frame = document.getElementById(FRAME_ID) as HTMLIFrameElement | null
  if (!frame) {
    frame = document.createElement('iframe')
    frame.id = FRAME_ID
    frame.hidden = true
    frame.setAttribute('aria-hidden', 'true')
    document.body.appendChild(frame)
  }
  frame.src = `${BACKEND_URL}${path.startsWith('/') ? path : `/${path}`}`
}
