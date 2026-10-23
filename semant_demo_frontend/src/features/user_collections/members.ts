import type { UserSearchResult } from 'src/generated/api'

/** How a collection member (or a found user) is named: their name, else their username. */
export const memberName = (user: UserSearchResult) => user.name || user.username || 'Unknown user'
