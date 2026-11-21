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
