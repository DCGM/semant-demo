import { BACKEND_URL } from './config'

/**
 * Hands a backend download (e.g. `/api/exports/collections/<ticket>`, a path that is its own
 * credential) to the browser's download manager, which saves it straight to disk with its
 * progress; nothing is held in memory. The backend answers with `Content-Disposition:
 * attachment`, so the page stays where it is.
 */
export function startDownload (path: string): void {
  const link = document.createElement('a')
  link.href = `${BACKEND_URL}${path.startsWith('/') ? path : `/${path}`}`
  link.rel = 'noopener'
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  link.remove()
}
