import type { AiSuggestionRunInfo } from 'src/generated/api'
import { useApi } from 'src/shared/api'

export type { AiSuggestionRunInfo } from 'src/generated/api'

function progress (run: AiSuggestionRunInfo): string | null {
  const total = run.unitsTotal ?? 0
  if (total <= 0) return null
  const completed = run.unitsCompleted ?? 0
  const unit = run.unit === 'call' ? 'call' : run.unit === 'selection' ? 'selection'
    : run.unit === 'tag' ? 'tag' : 'chunk'
  const plural = total === 1 ? unit : `${unit}s`
  return `${completed}/${total} ${plural}`
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
  const outcome = run.outcome ?? 'running'
  const label = name[outcome] ?? outcome
  const count = progress(run)
  return count ? `${label} · ${count}` : label
}

export function runOutcomeDescription (run: AiSuggestionRunInfo): string {
  const count = progress(run)
  const progressText = count ? `${count} completed. ` : ''
  const savedText = `${run.saved ?? 0} suggestion(s) saved.`
  const failures = [
    run.providerFailures ? `${run.providerFailures} AI operation(s) failed.` : '',
    run.saveFailures ? `${run.saveFailures} suggestion(s) could not be saved.` : ''
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
  return await useApi().default.listSuggestionRunsApiAiSuggestionRunsGet({ collectionId, documentId })
}

/** Unknown includes spans saved before #801 and provenance-less collections. */
export function matchesAiRun (runId: string | null | undefined,
  selected: string | null, knownRuns: Set<string>): boolean {
  if (selected === null) return true
  if (selected === 'legacy') return !runId || !knownRuns.has(runId)
  return runId === selected
}
