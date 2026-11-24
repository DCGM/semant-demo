import { API_CREDENTIALS, apiUrl, authHeaders } from 'src/shared/api'
import { apiErrorFromResponse } from 'src/shared/api/errors'

/** Read-only run history; the backend checks collection/document read access. */
export interface AiSuggestionRunInfo {
  id: string
  mode: 'optimized' | 'thorough' | 'selection'
  config_name: string
  tag_ids: string[]
  started_at: string
  finished_at: string | null
  outcome: string
  saved: number
  unit: 'chunk' | 'call' | 'tag' | 'selection'
  units_total: number
  units_completed: number
  provider_failures: number
  save_failures: number
}

function progress (run: AiSuggestionRunInfo): string | null {
  if (run.units_total <= 0) return null
  const unit = run.unit === 'call' ? 'call' : run.unit === 'selection' ? 'selection'
    : run.unit === 'tag' ? 'tag' : 'chunk'
  const plural = run.units_total === 1 ? unit : `${unit}s`
  return `${run.units_completed}/${run.units_total} ${plural}`
}

/** Short status in the run picker; full explanation is shown below the picker. */
export function runOutcomeLabel (run: AiSuggestionRunInfo): string {
  const name: Record<string, string> = {
    complete: 'Completed',
    partial: 'Partially completed',
    failed: 'Failed',
    cancelled: 'Cancelled',
    interrupted: 'Interrupted',
    running: 'Running'
  }
  const label = name[run.outcome] ?? run.outcome
  const count = progress(run)
  return count ? `${label} · ${count}` : label
}

export function runOutcomeDescription (run: AiSuggestionRunInfo): string {
  const count = progress(run)
  const progressText = count ? `${count} completed. ` : ''
  const savedText = `${run.saved} suggestion(s) saved.`
  const failures = [
    run.provider_failures ? `${run.provider_failures} AI operation(s) failed.` : '',
    run.save_failures ? `${run.save_failures} suggestion(s) could not be saved.` : ''
  ].filter(Boolean).join(' ')
  if (run.outcome === 'failed') {
    return `Failed: no AI call completed successfully and no suggestions were saved. ${progressText}${failures}`.trim()
  }
  if (run.outcome === 'cancelled') {
    return `Stopped before completion. ${progressText}${savedText}`
  }
  if (run.outcome === 'partial') {
    return `Partially completed: some operations failed or the run stopped early. ${progressText}${savedText} ${failures}`.trim()
  }
  if (run.outcome === 'complete') return `Completed. ${progressText}${savedText}`
  if (run.outcome === 'interrupted') return 'Run did not record its completion; saved suggestions remain available.'
  if (run.outcome === 'running') return 'Run is still in progress.'
  return `Run status: ${run.outcome}. ${savedText}`
}

export async function loadAiRunHistory (collectionId: string, documentId: string): Promise<AiSuggestionRunInfo[]> {
  const params = new URLSearchParams({ collection_id: collectionId, document_id: documentId })
  const headers = authHeaders()
  const response = await fetch(apiUrl(`/ai/suggestion_runs?${params.toString()}`), {
    headers, credentials: API_CREDENTIALS
  })
  if (!response.ok) throw await apiErrorFromResponse(response)
  return await response.json() as AiSuggestionRunInfo[]
}

/** Unknown includes spans saved before #801 and provenance-less collections. */
export function matchesAiRun (runId: string | null | undefined,
  selected: string | null, knownRuns: Set<string>): boolean {
  if (selected === null) return true
  if (selected === 'legacy') return !runId || !knownRuns.has(runId)
  return runId === selected
}
