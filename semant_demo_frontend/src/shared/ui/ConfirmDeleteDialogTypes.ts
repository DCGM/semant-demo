export interface ConfirmDeleteOptions {
  title: string
  /** What is deleted, as plain text (names are not HTML). */
  message: string
  okLabel?: string
  /** What else would be deleted along, as text (e.g. "3 approved annotations"); empty when nothing. */
  alsoDeletes: () => Promise<string>
}
