import { SummaryLength } from 'src/generated/api'

/**
 * Length levels of an AI summary (#360), shared by the search and document summaries. The
 * server configuration defines what each level means (words and token limit).
 */
export const SUMMARY_LENGTH_OPTIONS: { label: string, value: SummaryLength }[] = [
  { label: 'Short', value: SummaryLength.short },
  { label: 'Detailed', value: SummaryLength.detailed }
]

export const SUMMARY_LENGTH_DEFAULT: SummaryLength = SummaryLength.short

/** The conversation's question for a summary of this length, e.g. "Summarize (short)". */
export function summaryPrompt (length: SummaryLength): string {
  const option = SUMMARY_LENGTH_OPTIONS.find(o => o.value === length)
  return `Summarize (${(option?.label ?? length).toLowerCase()})`
}
