import { readStored, removeStored, storedKeys, writeStored } from 'src/shared/browserStorage'

// The tags last chosen for AI runs in a collection, remembered per user and collection in
// this browser (#770), so folded run options are ready to run after a reload. Another user
// of the browser never gets them preselected.
const PREFIX = 'semant.aiRunTags.'

const key = (userId: string, collectionId: string) => `${PREFIX}${userId}.${collectionId}`

/** The remembered tag ids; none for a signed-out user or when nothing usable is stored. */
export function readRunTags (userId: string | undefined, collectionId: string): string[] {
  if (!userId) return []
  try {
    const stored: unknown = JSON.parse(readStored(key(userId, collectionId)) ?? '[]')
    return Array.isArray(stored) ? stored.filter((id): id is string => typeof id === 'string') : []
  } catch {
    return []
  }
}

export function writeRunTags (userId: string | undefined, collectionId: string, tagIds: string[]): void {
  if (userId) writeStored(key(userId, collectionId), JSON.stringify(tagIds))
}

/** Forgets the remembered tags of deleted collections, for every user of this browser. */
export function forgetRunTags (collectionIds: readonly string[]): void {
  const ids = new Set(collectionIds)
  for (const stored of storedKeys(PREFIX)) {
    if (ids.has(stored.slice(stored.lastIndexOf('.') + 1))) removeStored(stored)
  }
}
