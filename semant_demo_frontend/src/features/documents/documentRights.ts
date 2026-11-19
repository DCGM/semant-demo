// The source rights of a corpus document (`Document.public`, #279), as Explore and the
// collection views show them. Public documents are readable by anyone and need no label; a
// restricted (`false`) or unknown (no value) document is readable only through a collection
// that holds it, and is labelled wherever such a collection shows it.

export type DocumentRights = 'public' | 'restricted' | 'unknown'

export function documentRights (value: boolean | null | undefined): DocumentRights {
  if (value === true) return 'public'
  return value === false ? 'restricted' : 'unknown'
}

export const RIGHTS_LABEL: Record<Exclude<DocumentRights, 'public'>, string> = {
  restricted: 'Restricted',
  unknown: 'Access unknown'
}

export const RIGHTS_HINT: Record<Exclude<DocumentRights, 'public'>, string> = {
  restricted: 'The source library does not make this document public. You can read it through this collection only.',
  unknown: 'The source library has not stated whether this document is public. You can read it through this collection only.'
}

/** The distinct documents among `documents` that are not public (restricted or unknown). */
export function nonPublicDocuments<T extends { id: string, _public?: boolean | null }> (documents: T[]): T[] {
  const seen = new Set<string>()
  return documents.filter(d => {
    if (d._public === true || seen.has(d.id)) return false
    seen.add(d.id)
    return true
  })
}

/**
 * The confirmation shown before restricted or unknown documents are linked to another
 * collection (#279, maintainer decision on #789): the link is the document's own route there,
 * independent of the collection it was found in.
 */
export function addRestrictedWarning (titles: string[], target: string): string {
  const shown = titles.slice(0, 5).map(t => `“${t || 'Untitled document'}”`).join(', ')
  const more = titles.length > 5 ? ` and ${titles.length - 5} more` : ''
  const one = titles.length === 1
  const what = one ? 'This document is' : `These ${titles.length} documents are`
  const it = one ? 'it' : 'them'
  return `${what} not public: ${shown}${more}. Adding ${it} to “${target}” gives everyone who can read that ` +
    `collection lasting access to the full text and scans, also after the collection you found ${it} in stops ` +
    'being shared with you, and also when you share the target collection. No copy is made: the collection ' +
    `links to the same corpus ${one ? 'document' : 'documents'}.`
}
