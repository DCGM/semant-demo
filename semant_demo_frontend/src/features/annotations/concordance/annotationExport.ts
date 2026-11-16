import {
  AnnotationExportScope, CsvDelimiter, SpanType, type AnnotationExportRequest
} from 'src/generated/api'
import { apiErrorMessage, errorStatus, isAbortError, useApi } from 'src/shared/api'
import { plural } from 'src/shared/plural'
import { annotationFilters, type ConcordanceFilters } from './concordanceStore'
import type { ConcordanceChip } from './filterChips'

/**
 * CSV export of the workspace's annotations (#719): what to export and which column groups,
 * the request for the server, and the download. The server
 * aborts it, rather than ending it early, when it cannot complete it; a download that does
 * not arrive whole is reported as failed and nothing is saved.
 */
export interface ExportOptions {
  scope: AnnotationExportScope
  /** Scope `collection`: the statuses to export (at least one). */
  types: SpanType[]
  documentMetadata: boolean
  chunkMetadata: boolean
  provenance: boolean
  delimiter: CsvDelimiter
}

export function defaultExportOptions (scope: AnnotationExportScope): ExportOptions {
  return {
    scope,
    types: [SpanType.pos, SpanType.auto, SpanType.neg],
    documentMetadata: true,
    chunkMetadata: false,
    provenance: false,
    delimiter: CsvDelimiter.comma
  }
}

export const SCOPE_NAMES: Record<AnnotationExportScope, string> = {
  [AnnotationExportScope.selection]: 'Selected annotations',
  [AnnotationExportScope.filters]: 'Current filter matches',
  [AnnotationExportScope.collection]: 'All annotations in the collection'
}

export const STATUS_NAMES: Record<SpanType, string> = {
  [SpanType.pos]: 'Confirmed',
  [SpanType.auto]: 'Proposals',
  [SpanType.neg]: 'Rejected'
}

/** The filters of the filter scope in words, the statuses always named ("Status: Confirmed, Proposals · Tag: Osoba"). */
export function exportFilterSummary (filters: ConcordanceFilters, chips: ConcordanceChip[]): string {
  const statuses = filters.types.map(t => STATUS_NAMES[t]).join(', ')
  return `Filters: ${[`Status: ${statuses}`, ...chips.filter(c => c.key !== 'types').map(c => `${c.group}: ${c.label}`)].join(' · ')}.`
}

/** The request of the options: the selection's ids, the current filters, or the chosen statuses. */
export function exportRequest (options: ExportOptions, filters: ConcordanceFilters,
  selectedIds: Iterable<string>): AnnotationExportRequest {
  const groups = {
    documentMetadata: options.documentMetadata,
    chunkMetadata: options.chunkMetadata,
    provenance: options.provenance,
    delimiter: options.delimiter
  }
  switch (options.scope) {
    case AnnotationExportScope.selection:
      return { scope: options.scope, annotationIds: [...selectedIds], ...groups }
    case AnnotationExportScope.filters:
      return { scope: options.scope, filters: annotationFilters(filters), ...groups }
    default:
      return { scope: AnnotationExportScope.collection, types: [...options.types], ...groups }
  }
}

export interface ExportResult {
  scope: AnnotationExportScope
  /** Rows in the file, one per annotation. */
  count: number
  /** Selected ids that are no annotation of the collection (any more). */
  missing: number
  filename: string
}

/** The file name of a `Content-Disposition` header, or `fallback`. */
export function filenameOf (disposition: string | null, fallback: string): string {
  const match = disposition?.match(/filename="([^"]+)"/)
  return match?.[1] ?? fallback
}

/** Saves `blob` as a downloaded file named `filename`. */
export function saveFile (blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Revoked after the browser has started the download.
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

/** Thrown when the file did not arrive whole (the connection or the server's export was interrupted). */
export class InterruptedDownload extends Error {
  constructor () {
    super('The download was interrupted')
    this.name = 'InterruptedDownload'
  }
}

/**
 * Exports, downloads the whole file and only then saves it. `InterruptedDownload` when the
 * body did not arrive whole; the request's own errors (400, 404, 422, network) otherwise.
 */
export async function downloadExport (collectionId: string, request: AnnotationExportRequest,
  signal?: AbortSignal, save: typeof saveFile = saveFile): Promise<ExportResult> {
  const response = await useApi().default.exportCollectionAnnotationsApiUserCollectionsCollectionIdAnnotationsExportPostRaw(
    { collectionId, annotationExportRequest: request }, { signal })
  const raw = response.raw
  let blob: Blob
  try {
    blob = await raw.blob()
  } catch (e) {
    if (isAbortError(e)) throw e
    throw new InterruptedDownload()
  }
  const result: ExportResult = {
    scope: request.scope,
    count: Number(raw.headers.get('X-Export-Count') ?? NaN),
    missing: Number(raw.headers.get('X-Export-Missing') ?? 0),
    filename: filenameOf(raw.headers.get('Content-Disposition'), `annotations-${request.scope}.csv`)
  }
  save(blob, result.filename)
  return result
}

/** A message for a failed export. */
export async function exportFailure (e: unknown): Promise<string> {
  if (e instanceof InterruptedDownload) {
    return 'The download was interrupted before the file was complete, so nothing was saved. ' +
      'This happens when the annotations change during the export or the connection fails; try again.'
  }
  const status = errorStatus(e)
  if (status === 404) return 'This collection is not available to you.'
  if (status === 400 || status === 422 || status === 503) {
    return await apiErrorMessage(e, 'These annotations cannot be exported; narrow the filters.')
  }
  console.error('Exporting the annotations failed', e)
  return 'The export failed; nothing was saved. Try again.'
}

/** What a finished export saved, for the dialog. */
export function resultText (result: ExportResult): string {
  const rows = Number.isFinite(result.count) ? plural(result.count, 'annotation') : 'The annotations'
  const missing = result.missing > 0
    ? ` ${plural(result.missing, 'selected annotation no longer exists', 'selected annotations no longer exist')} and ${result.missing === 1 ? 'was' : 'were'} not exported.`
    : ''
  return `Saved ${result.filename}: ${rows} (${SCOPE_NAMES[result.scope].toLowerCase()}).${missing}`
}
