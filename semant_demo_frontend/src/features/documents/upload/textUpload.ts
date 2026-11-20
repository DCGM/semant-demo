import type { TextUploadFileResult, TextUploadResponse } from 'src/generated/api'

// Upload of private plain-text documents into a collection (#785, docs/TEXT_UPLOAD.md). The
// backend validates everything again; these checks only spare a round trip.

/** The metadata CSV template (docs/TEXT_UPLOAD.md); `filename` is required, the rest optional. */
export const CSV_TEMPLATE =
  'filename,title,author,yearIssued,language\r\n' +
  'example.txt,Example document,Jane Doe,1925,ces\r\n'

/** The CSV's `language` codes: the Language search filter's (blank is allowed too). */
export const LANGUAGES = ['ces', 'deu', 'hun', 'lat', 'zxx'] as const

export const MAX_FILES = 20
export const MAX_FILE_BYTES = 2_000_000

export type UploadStatus = TextUploadFileResult['status']

/** A file's status as the dialog shows it. */
export const STATUS: Record<UploadStatus, { label: string, icon: string, color: string }> = {
  completed: { label: 'Added', icon: 'check_circle', color: 'positive' },
  invalid: { label: 'Invalid', icon: 'error', color: 'negative' },
  not_written: { label: 'Not uploaded', icon: 'block', color: 'grey-7' },
  failed: { label: 'Failed', icon: 'error', color: 'negative' },
  uncertain: { label: 'Unconfirmed', icon: 'help', color: 'warning' }
}

/** Problems the server would refuse anyway, by file name ('' for the whole selection). */
export function checkFiles (files: readonly File[]): Map<string, string> {
  const problems = new Map<string, string>()
  if (files.length > MAX_FILES) problems.set('', `At most ${MAX_FILES} files can be uploaded at once.`)
  const seen = new Set<string>()
  for (const file of files) {
    if (!file.name.toLowerCase().endsWith('.txt')) problems.set(file.name, 'Only .txt files can be uploaded.')
    else if (file.size > MAX_FILE_BYTES) problems.set(file.name, `The file is larger than ${MAX_FILE_BYTES / 1_000_000} MB.`)
    else if (file.size === 0) problems.set(file.name, 'The file is empty.')
    else if (seen.has(file.name)) problems.set(file.name, 'Another file has the same name; rename one of them.')
    seen.add(file.name)
  }
  return problems
}

/**
 * Copies of the selected files, read now, and the files that could not be read. A browser
 * refuses to send a file that changed on disk after it was selected (Chrome fails the whole
 * request with net::ERR_UPLOAD_FILE_CHANGED, which reaches the page as a bare network error);
 * reading each file first names it instead, and the copies are what is sent.
 */
export async function readSelection (files: readonly File[]): Promise<{ copies: File[], unreadable: File[] }> {
  const copies: File[] = []
  const unreadable: File[] = []
  for (const file of files) {
    try {
      copies.push(new File([await file.arrayBuffer()], file.name, { type: file.type, lastModified: file.lastModified }))
    } catch {
      unreadable.push(file)
    }
  }
  return { copies, unreadable }
}

/** Why nothing was sent when `names` could not be read. */
export function unreadableMessage (names: readonly string[]): string {
  const one = names.length === 1
  return `${names.join(', ')} ${one ? 'has' : 'have'} changed or can no longer be read since ${one ? 'it was' : 'they were'} ` +
    `selected, so nothing was uploaded. Select ${one ? 'it' : 'them'} again, then upload.`
}

/** Whether the server saved every file of the response. */
export const allCompleted = (response: TextUploadResponse): boolean =>
  !response.errors?.length && response.files.every(f => f.status === 'completed')

/**
 * The files still to upload after a response: every file that was not saved (failed, invalid
 * or not sent because of another file). Saved files, also unconfirmed ones, leave the
 * selection, so uploading again never creates a second copy of them.
 */
export function filesNotSaved (files: readonly File[], response: TextUploadResponse): File[] {
  const saved = new Set(response.files.filter(f => f.status === 'completed' || f.status === 'uncertain').map(f => f.filename))
  return files.filter(file => !saved.has(file.name))
}

export function summary (response: TextUploadResponse): string {
  const added = response.files.filter(f => f.status === 'completed').length
  const total = response.files.length
  if (added === total && !response.errors?.length) return total === 1 ? 'The document was added.' : `All ${total} documents were added.`
  if (!added) return 'No document was added.'
  return `${added} of ${total} documents were added.`
}
