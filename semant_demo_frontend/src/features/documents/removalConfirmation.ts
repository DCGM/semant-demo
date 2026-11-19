import type { DocumentStats } from 'src/generated/api'
import { plural } from 'src/shared/plural'

/** A document to remove from the collection, with its stats unless they are unavailable. */
export interface RemovalTarget {
  title: string
  stats?: DocumentStats | null
}

export interface RemovalConfirmation {
  title: string
  message: string
  okLabel: string
}

// Removing a document only unlinks it (and its chunks) from the collection: its annotations
// stay stored (the Annotations tab, the export and deleting their tag still include them),
// but the document cannot be opened in the collection until it is added back (#765). The
// wording must never claim they are deleted or entirely hidden.
const NOT_OPENABLE = 'the document cannot be opened in this collection until it is added back.'

function describeCounts (annotations: number, suggestions: number): string {
  const parts = []
  if (annotations) parts.push(plural(annotations, 'confirmed annotation'))
  if (suggestions) parts.push(plural(suggestions, 'pending AI suggestion'))
  return parts.join(' and ')
}

const annotationsOf = (stats: DocumentStats) => stats.annotationsCount
const suggestionsOf = (stats: DocumentStats) => stats.suggestionsCount ?? 0

/**
 * Confirmation of removing one document from the collection. A document with confirmed
 * annotations or pending AI suggestions gets a stronger warning naming them; a document
 * whose stats are unavailable is never described as having none.
 */
export function singleRemovalConfirmation ({ title, stats }: RemovalTarget): RemovalConfirmation {
  const question = `Remove the document "${title}" from the collection?`
  if (!stats) {
    return {
      title: 'Remove Document',
      message: `${question} Its annotation count could not be loaded. Any annotations it has are not deleted, but ${NOT_OPENABLE}`,
      okLabel: 'Remove'
    }
  }
  const annotations = annotationsOf(stats)
  const suggestions = suggestionsOf(stats)
  if (!annotations && !suggestions) {
    return { title: 'Remove Document', message: question, okLabel: 'Remove' }
  }
  const kept = annotations + suggestions === 1 ? 'It is' : 'They are'
  return {
    title: annotations ? 'Remove Annotated Document' : 'Remove Document',
    message: `"${title}" has ${describeCounts(annotations, suggestions)} in this collection. ` +
      `${kept} not deleted, but ${NOT_OPENABLE}`,
    okLabel: 'Remove'
  }
}

/**
 * Confirmation of removing several documents: how many of them have known annotations
 * or suggestions and their totals, and how many have unavailable stats.
 */
export function bulkRemovalConfirmation (targets: RemovalTarget[]): RemovalConfirmation {
  const known = targets.flatMap(({ stats }) => (stats ? [stats] : []))
  const unknown = targets.length - known.length
  const annotated = known.filter((s) => annotationsOf(s) || suggestionsOf(s))
  const annotations = annotated.reduce((sum, s) => sum + annotationsOf(s), 0)
  const suggestions = annotated.reduce((sum, s) => sum + suggestionsOf(s), 0)

  const sentences = [`Remove ${plural(targets.length, 'selected document')} from the collection?`]
  if (annotated.length) {
    sentences.push(
      `${annotated.length} of them ${annotated.length === 1 ? 'has' : 'have'} annotations in this collection ` +
      `(${describeCounts(annotations, suggestions)} in total).`
    )
  }
  if (unknown) {
    sentences.push(`The annotation count of ${plural(unknown, 'document')} could not be loaded.`)
  }
  if (annotated.length || unknown) {
    sentences.push('Annotations are not deleted, but a removed document cannot be opened in this collection until it is added back.')
  }
  return {
    title: annotations ? 'Remove Annotated Documents' : 'Remove Selected Documents',
    message: sentences.join(' '),
    okLabel: 'Remove selected'
  }
}
