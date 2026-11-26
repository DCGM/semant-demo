import {
  AnnotationExportScope, CsvDelimiter, ExportFormat, SpanType, type AnnotationExportRequest
} from 'src/generated/api'
import { apiErrorMessage, errorStatus, isAbortError, useApi } from 'src/shared/api'
import { plural } from 'src/shared/plural'
import { annotationFilters, ranking, type ConcordanceFilters } from './concordanceStore'
import type { ConcordanceChip } from './filterChips'

/**
 * CSV or JSON export of the workspace's annotations (#719, #826): what to export and which column groups,
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
  format: ExportFormat
  /** JSON only: also list values retained on rejected, proposed or inapplicable annotations, apart. */
  audit: boolean
}

export function defaultExportOptions (scope: AnnotationExportScope): ExportOptions {
  return {
    scope,
    types: [SpanType.pos, SpanType.auto, SpanType.neg],
    documentMetadata: true,
    chunkMetadata: false,
    provenance: false,
    delimiter: CsvDelimiter.comma,
    format: ExportFormat.csv,
    audit: false
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
  const json = options.format === ExportFormat.json
  const groups = {
    documentMetadata: options.documentMetadata,
    chunkMetadata: options.chunkMetadata,
    provenance: options.provenance,
    delimiter: options.delimiter,
    format: options.format,
    ...(json && options.audit ? { audit: true } : {})
  }
  switch (options.scope) {
    case AnnotationExportScope.selection:
      return { scope: options.scope, annotationIds: [...selectedIds], ...groups }
    case AnnotationExportScope.filters:
      // A ranked result exports exactly its top k, labeled so in the manifest.
      return { scope: options.scope, filters: annotationFilters(filters), ranking: ranking(filters), ...groups }
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
  /** JSON: annotations deleted during the export, listed in its completion; 0 when none. */
  deleted: number
}

/**
 * The closing `completion` of a JSON export, read from the end of the file; `InterruptedDownload`
 * when it is missing (a file without it is cut short and not valid JSON).
 */
export async function jsonCompletion (blob: Blob): Promise<{ complete: boolean, missingIds: string[] }> {
  const tail = await blob.slice(Math.max(0, blob.size - 1_000_000)).text()
  const start = tail.lastIndexOf('],"completion":')
  if (start < 0 || !tail.endsWith('}')) throw new InterruptedDownload()
  try {
    const completion = JSON.parse(tail.slice(start + '],"completion":'.length, -1))
    return { complete: completion.complete === true, missingIds: completion.missing_ids ?? [] }
  } catch {
    throw new InterruptedDownload()
  }
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
  const completion = request.format === ExportFormat.json ? await jsonCompletion(blob) : null
  const result: ExportResult = {
    scope: request.scope,
    count: Number(raw.headers.get('X-Export-Count') ?? NaN),
    missing: Number(raw.headers.get('X-Export-Missing') ?? 0),
    filename: filenameOf(raw.headers.get('Content-Disposition'), `annotations-${request.scope}.${request.format === ExportFormat.json ? 'json' : 'csv'}`),
    deleted: completion?.missingIds.length ?? 0
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
  const deleted = result.deleted > 0
    ? ` ${plural(result.deleted, 'annotation was', 'annotations were')} deleted during the export and ${result.deleted === 1 ? 'is' : 'are'} listed in the file's completion: it is not a complete dataset.`
    : ''
  return `Saved ${result.filename}: ${rows} (${SCOPE_NAMES[result.scope].toLowerCase()}).${missing}${deleted}`
}
