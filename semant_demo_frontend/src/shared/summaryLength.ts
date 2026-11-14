import { SummaryLength } from 'src/generated/api'

/**
 * Length levels of an AI summary (#360), offered as AI Chat's suggested messages. The server
 * configuration defines what each level means (words and token limit).
 */
export const SUMMARY_LENGTHS: readonly SummaryLength[] = [SummaryLength.short, SummaryLength.detailed]

/** The conversation's question for a summary of this length (also its suggested message). */
export function summaryPrompt (length: SummaryLength): string {
  return length === SummaryLength.detailed ? 'Summarize in detail' : 'Summarize briefly'
}
