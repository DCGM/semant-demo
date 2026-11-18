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
