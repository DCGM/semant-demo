/**
 * Links to the original digitized document in its source digital library (#255).
 *
 * Corpus documents come from Kramerius libraries: a document's id is its Kramerius
 * record UUID and a chunk's `startPageId` the UUID of its first page, in the library named
 * by the document's `library` code (filled from the library's own metadata row by
 * `metadata_sync`). The Czech Digital Library client opens them as
 * `https://www.digitalniknihovna.cz/<code>/view/uuid:<document>?page=uuid:<page>`
 * (its routes `:k/view/:uuid` with a `page` query; checked 2026-10-14).
 *
 * A link is built only from a known library code and well-formed UUIDs; anything else
 * (no library, an unknown code, a malformed id) gives no link rather than a guessed one.
 */

const VIEWER = 'https://www.digitalniknihovna.cz'

/**
 * Library codes the digitalniknihovna.cz client serves (its `krameriusList` in
 * `assets/shared/globals.js`, checked 2026-10-14). They equal the `library` codes of the
 * Kramerius metadata mirror. A code missing here gives no link; add it after checking that
 * the client lists it.
 */
export const DIGITAL_LIBRARY_CODES: ReadonlySet<string> = new Set([
  'mzk', 'nkp', 'knav', 'svkhk', 'ntk', 'svkul', 'kfbz', 'kkp', 'svkkl', 'mlp', 'nlk', 'uzei',
  'cbvk', 'kkkv', 'kvkli', 'vkol', 'svkos', 'svkpk', 'kkvhb', 'mkct', 'cuni', 'cuni_lf1',
  'cuni_fsv', 'vse', 'vsup', 'mjh', 'nm', 'npmk', 'zmp', 'upm', 'zcm', 'hmt', 'nacr', 'nfa',
  'lmda', 'dsmo', 'vugtk', 'd', 'nulk', 'cdk', 'idu', 'cro', 'cvti', 'snk', 'eod'
])

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** The bare lowercase UUID of `value` (also with a Kramerius `uuid:` prefix), or null. */
function krameriusUuid (value: unknown): string | null {
  if (typeof value !== 'string') return null
  const bare = value.trim().replace(/^uuid:/i, '')
  return UUID.test(bare) ? bare.toLowerCase() : null
}

export interface SourceDocument {
  id: string
  library?: string | null
}

/**
 * The URL of the original digitized document in its digital library, opened at `pageId`
 * when that is a well-formed page UUID; null when no trustworthy link can be built.
 */
export function originalSourceUrl (document: SourceDocument | null | undefined, pageId?: string | null): string | null {
  if (!document) return null
  const library = typeof document.library === 'string' ? document.library.trim().toLowerCase() : ''
  if (!DIGITAL_LIBRARY_CODES.has(library)) return null
  const id = krameriusUuid(document.id)
  if (!id) return null
  const url = `${VIEWER}/${library}/view/uuid:${id}`
  const page = krameriusUuid(pageId)
  return page ? `${url}?page=uuid:${page}` : url
}
