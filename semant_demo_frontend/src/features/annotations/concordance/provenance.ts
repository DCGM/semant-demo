import type { CollectionPerson } from 'src/generated/api'

/**
 * Names for the actors recorded on annotations (#460): the signed-in user is "you", the
 * collection's owner and members by name, anyone else (no longer a member, or a removed
 * account) as "a former member".
 */
export function personName (id: string | null | undefined, people: CollectionPerson[], me: string | null | undefined): string {
  if (!id) return 'someone'
  if (id === me) return 'you'
  const person = people.find(p => p.id === id)
  return person ? person.name || person.username || 'a member' : 'a former member'
}

/** A recorded time, short and in the reader's locale. */
export function formatWhen (when: Date | null | undefined): string {
  if (!when) return ''
  return when.toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}
