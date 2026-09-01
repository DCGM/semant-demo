const MINOR_TITLE_CASE_WORDS = new Set([
  'a', 'an', 'the', 'and', 'or', 'but', 'nor', 'to', 'of', 'in', 'on', 'for', 'at', 'by', 'with'
])

function titleCase (words: string[]): string {
  return words
    .map((word, i) => (i > 0 && MINOR_TITLE_CASE_WORDS.has(word.toLowerCase()))
      ? word.toLowerCase()
      : word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

// Frontend counterpart of the backend's _format_user_form (semant_demo/search_filters.py):
// turns a snake_case backend value (e.g. "ddc_500_natural_sciences") into a display label.
export function formatUserForm (backendValue: string): string {
  if (backendValue.startsWith('ddc_')) {
    const parts = backendValue.split('_')
    const prefix = parts[0].toUpperCase()
    const code = parts[1] ?? ''
    const rest = titleCase(parts.slice(2))
    return `${prefix} ${code} ${rest}`.trim()
  }
  return titleCase(backendValue.split('_'))
}
