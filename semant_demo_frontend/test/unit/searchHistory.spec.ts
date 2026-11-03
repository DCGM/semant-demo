import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { Quasar } from 'quasar'

import { SearchType, type SearchFilter } from 'src/generated/api'
import {
  DISPLAY_LIMIT,
  HISTORY_LIMIT,
  MAX_QUERY_LENGTH,
  matchingEntries,
  parseHistory,
  readHistory,
  serializeHistory,
  storageKey,
  withEntry,
  writeHistory,
  type HistoryAudience,
  type HistoryCriteria,
  type HistoryEntry
} from 'src/shared/searchHistory/history'
import { useSearchHistory } from 'src/shared/searchHistory/useSearchHistory'
import SearchHistoryDropdown from 'src/shared/searchHistory/SearchHistoryDropdown.vue'
import {
  criteriaOfRequest,
  describeCriteria,
  restoreSearch,
  SEARCH_CRITERIA_VERSION,
  searchHistoryCriteria,
  type SearchHistoryCriteria,
  type SearchOptions
} from 'src/features/search/searchHistoryCriteria'

// Recent search history (#558): kept in this browser, one history per signed-in user and one
// for signed-out use, at most 50 entries of which 10 are shown at once.

const ANONYMOUS: HistoryAudience = { kind: 'anonymous' }
const ALICE: HistoryAudience = { kind: 'user', userId: 'alice' }
const BOB: HistoryAudience = { kind: 'user', userId: 'bob' }

/**
 * Criteria of the generic tests: a single tag compared as is, in format 2. Format 1 stored
 * a tag number, converted to `tag-<n>`; a format 1 tag that is not a number is left out.
 */
const tagCriteria: HistoryCriteria<string> = {
  namespace: 'test',
  version: 2,
  parse: (raw, version) => {
    if (version === 1) return typeof raw === 'number' ? `tag-${raw}` : null
    return typeof raw === 'string' ? raw : null
  },
  key: (c) => c
}

/** Stores `list` as an audience's whole history. */
const save = (audience: HistoryAudience, list: HistoryEntry<string>[]) => writeHistory(audience, tagCriteria, list)

const entry = (query: string, savedAt: number, criteria = ''): HistoryEntry<string> => ({ query, criteria, savedAt })

/** `count` entries, the newest (`query-<count-1>`) first. */
function entries (count: number): HistoryEntry<string>[] {
  return Array.from({ length: count }, (_, i) => entry(`query-${i}`, 1000 + i)).reverse()
}

const stored = (value: unknown) => JSON.stringify(value)

beforeEach(() => localStorage.clear())
afterEach(() => { vi.restoreAllMocks() })

describe('history list', () => {
  it('adds the newest first and moves a repeated search to the top instead of duplicating it', () => {
    let list: HistoryEntry<string>[] = []
    list = withEntry(list, entry('a', 1), tagCriteria)
    list = withEntry(list, entry('b', 2), tagCriteria)
    list = withEntry(list, entry('a', 3), tagCriteria)
    expect(list.map(e => [e.query, e.savedAt])).toEqual([['a', 3], ['b', 2]])
  })

  it('keeps the same query with other criteria as a separate entry', () => {
    const list = withEntry([entry('a', 1, 'cs')], entry('a', 2, 'de'), tagCriteria)
    expect(list.map(e => e.criteria)).toEqual(['de', 'cs'])
  })

  it('keeps at most 50 entries and drops the oldest first', () => {
    const list = withEntry(entries(HISTORY_LIMIT), entry('newest', 9999), tagCriteria)
    expect(list).toHaveLength(HISTORY_LIMIT)
    expect(list[0].query).toBe('newest')
    expect(list.some(e => e.query === 'query-0')).toBe(false)
    expect(list.some(e => e.query === 'query-1')).toBe(true)
  })

  it('shows at most 10, also when filtering, and matches beyond the newest 10', () => {
    const list = entries(HISTORY_LIMIT)
    expect(matchingEntries(list, '').map(e => e.query)).toEqual(list.slice(0, DISPLAY_LIMIT).map(e => e.query))
    // query-3 is among the oldest: not shown without text, found by typing.
    expect(matchingEntries(list, 'QUERY-3 ').map(e => e.query)).toEqual(['query-39', 'query-38', 'query-37', 'query-36', 'query-35', 'query-34', 'query-33', 'query-32', 'query-31', 'query-30'])
    expect(matchingEntries(list, 'query-3').length).toBe(DISPLAY_LIMIT)
    expect(matchingEntries(list, 'y-3').some(e => e.query === 'query-3')).toBe(false)
    expect(matchingEntries(list, 'query-3', 50).some(e => e.query === 'query-3')).toBe(true)
  })
})

describe('stored history', () => {
  it('keeps a separate history per signed-in user and for signed-out use', () => {
    save(ALICE, [entry('alice search', 1)])
    save(BOB, [entry('bob search', 1)])
    save(ANONYMOUS, [entry('guest search', 1)])
    expect(readHistory(ALICE, tagCriteria).entries.map(e => e.query)).toEqual(['alice search'])
    expect(readHistory(BOB, tagCriteria).entries.map(e => e.query)).toEqual(['bob search'])
    expect(readHistory(ANONYMOUS, tagCriteria).entries.map(e => e.query)).toEqual(['guest search'])
    expect(Object.keys(localStorage).sort()).toEqual([
      'semant.searchHistory.test.anonymous',
      'semant.searchHistory.test.user.alice',
      'semant.searchHistory.test.user.bob'
    ])
  })

  it('removes the key when the history becomes empty', () => {
    save(ALICE, [entry('a', 1)])
    save(ALICE, [])
    expect(localStorage.getItem(storageKey('test', ALICE))).toBeNull()
  })

  it('ignores a malformed stored value', () => {
    const malformed = [
      'not json',
      '[]',
      'null',
      stored({ version: 1, criteriaVersion: 2, entries: 'x' }),
      stored({ version: 1, entries: [] }),
      stored({ version: 1, criteriaVersion: 1.5, entries: [] }),
      stored({ version: 0, criteriaVersion: 2, entries: [] }),
      stored({ version: '2', criteriaVersion: 2, entries: [] })
    ]
    for (const value of malformed) {
      expect(parseHistory(value, tagCriteria)).toEqual({ entries: [], newerFormat: false })
    }
  })

  it('leaves out malformed entries and keeps the valid ones, newest first', () => {
    const value = stored({
      version: 1,
      criteriaVersion: 2,
      entries: [
        { query: 'old', criteria: '', savedAt: 1 },
        { query: 'new', criteria: '', savedAt: 5 },
        { query: 42, criteria: '', savedAt: 2 },
        { query: '   ', criteria: '', savedAt: 3 },
        { query: 'bad criteria', criteria: 7, savedAt: 4 },
        { query: 'no time', criteria: '' },
        { query: 'x'.repeat(MAX_QUERY_LENGTH + 1), criteria: '', savedAt: 6 },
        { query: 'new', criteria: '', savedAt: 0 },
        null,
        '<img src=x onerror=alert(1)>'
      ]
    })
    expect(parseHistory(value, tagCriteria).entries.map(e => e.query)).toEqual(['new', 'old'])
  })

  it('keeps no more than 50 stored entries', () => {
    expect(parseHistory(serializeHistory(entries(80), tagCriteria), tagCriteria).entries).toHaveLength(HISTORY_LIMIT)
  })

  it('stores the format of the list and of the criteria apart', () => {
    save(ALICE, [entry('a', 1, 'cs')])
    expect(JSON.parse(localStorage.getItem(storageKey('test', ALICE)) ?? '')).toEqual({
      version: 1,
      criteriaVersion: 2,
      entries: [{ query: 'a', savedAt: 1, criteria: 'cs' }]
    })
  })

  it('reads an older criteria format through the search input, which converts it or leaves it out', () => {
    const value = stored({
      version: 1,
      criteriaVersion: 1,
      entries: [
        { query: 'converted', criteria: 7, savedAt: 2 },
        { query: 'not convertible', criteria: 'cs', savedAt: 3 }
      ]
    })
    expect(parseHistory(value, tagCriteria)).toEqual({ entries: [entry('converted', 2, 'tag-7')], newerFormat: false })
  })

  it('neither reads nor writes over a history of a newer format', () => {
    for (const newer of [{ version: 2, criteriaVersion: 2 }, { version: 1, criteriaVersion: 3 }]) {
      const value = stored({ ...newer, entries: [{ query: 'from a newer version', criteria: 'cs', savedAt: 5 }] })
      localStorage.setItem(storageKey('test', ALICE), value)
      expect(readHistory(ALICE, tagCriteria)).toEqual({ entries: [], newerFormat: true })

      const history = useSearchHistory(tagCriteria, ref<HistoryAudience | null>(ALICE), ref(''), () => undefined)
      history.show()
      expect(history.newerFormat.value).toBe(true)
      expect(history.shown.value).toBe(true) // the list asks for a reload
      expect(history.record('added', 'de')).toBe('skipped')
      history.clear()
      expect(localStorage.getItem(storageKey('test', ALICE))).toBe(value)
    }
  })

  it('notices a newer format written by another tab when changing the history', () => {
    save(ALICE, [entry('a', 1)])
    const history = useSearchHistory(tagCriteria, ref<HistoryAudience | null>(ALICE), ref(''), () => undefined)
    history.show()
    expect(history.entries.value).toHaveLength(1)
    const value = stored({ version: 1, criteriaVersion: 3, entries: [] })
    localStorage.setItem(storageKey('test', ALICE), value)
    expect(history.record('b', '')).toBe('skipped')
    expect(history.entries.value).toEqual([])
    expect(history.newerFormat.value).toBe(true)
    expect(localStorage.getItem(storageKey('test', ALICE))).toBe(value)
  })

  it('works without storage: nothing is read and nothing is remembered', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new Error('blocked') })
    expect(readHistory(ALICE, tagCriteria)).toEqual({ entries: [], newerFormat: false })
    expect(() => save(ALICE, [entry('a', 1)])).not.toThrow()
    expect(() => save(ALICE, [])).not.toThrow()
  })
})

describe('useSearchHistory', () => {
  function setup (audience: HistoryAudience | null = ALICE) {
    const who = ref<HistoryAudience | null>(audience)
    const text = ref('')
    const picked: HistoryEntry<string>[] = []
    const history = useSearchHistory(tagCriteria, who, text, (e) => picked.push(e))
    return { who, text, picked, history }
  }

  const key = (k: string, init: KeyboardEventInit = {}) => new KeyboardEvent('keydown', { key: k, cancelable: true, ...init })

  it('saves the query as typed without surrounding whitespace; not a blank or too long one', () => {
    const { history } = setup()
    expect(history.record('  old   gazette\n1848 ', 'cs')).toBe('saved')
    expect(history.record('   ', 'cs')).toBe('skipped')
    expect(history.record('x'.repeat(MAX_QUERY_LENGTH + 1), '')).toBe('tooLong')
    expect(history.record('y'.repeat(MAX_QUERY_LENGTH), '')).toBe('saved')
    expect(readHistory(ALICE, tagCriteria).entries.map(e => e.query)).toEqual(['y'.repeat(MAX_QUERY_LENGTH), 'old   gazette\n1848'])
  })

  it('treats queries differing only in whitespace as the same search', () => {
    const { history } = setup()
    history.record('old gazette', 'cs')
    history.record(' old   gazette ', 'cs')
    expect(readHistory(ALICE, tagCriteria).entries.map(e => e.query)).toEqual(['old   gazette'])
  })

  it('reads the stored history when the list opens, not on every keystroke', async () => {
    const { history, text } = setup()
    history.record('a', '')
    history.show()
    const getItem = vi.spyOn(Storage.prototype, 'getItem')
    text.value = 'a'
    history.show()
    await nextTick()
    expect(getItem).not.toHaveBeenCalled()
    history.close()
    history.show()
    expect(getItem).toHaveBeenCalledTimes(1)
  })

  it('leaves the arrow keys to the input when nothing is listed', async () => {
    const { history, text } = setup()
    history.record('gazette', '')
    history.show()
    text.value = 'no such search'
    await nextTick()
    const up = key('ArrowUp')
    expect(history.onKeydown(up)).toBe(false)
    expect(up.defaultPrevented).toBe(false)
  })

  it('highlights within the history read when ArrowUp opens the list', () => {
    const { history } = setup()
    history.record('a', '')
    history.record('b', '')
    history.record('c', '')
    history.onKeydown(key('Escape'))
    // Another tab removed two searches meanwhile.
    save(ALICE, readHistory(ALICE, tagCriteria).entries.slice(0, 1))
    history.onKeydown(key('ArrowUp'))
    expect([history.suggestions.value.length, history.activeIndex.value]).toEqual([1, 0])
  })

  it('records nothing without a known audience', () => {
    const { history } = setup(null)
    expect(history.record('a', '')).toBe('skipped')
  })

  it('keeps a search recorded in another tab meanwhile', () => {
    const { history } = setup()
    history.record('first', '')
    save(ALICE, [entry('other tab', Date.now() + 1000), ...readHistory(ALICE, tagCriteria).entries])
    history.record('second', '')
    expect(readHistory(ALICE, tagCriteria).entries.map(e => e.query).sort()).toEqual(['first', 'other tab', 'second'])
  })

  it('follows the audience and records nothing while it is unknown', async () => {
    save(ALICE, [entry('alice search', 1)])
    save(ANONYMOUS, [entry('guest search', 1)])
    const { who, history } = setup(ANONYMOUS)
    expect(history.entries.value.map(e => e.query)).toEqual(['guest search'])

    who.value = ALICE
    await nextTick()
    expect(history.entries.value.map(e => e.query)).toEqual(['alice search'])

    // Signing out keeps Alice's history; the signed-out one is shown again, never merged.
    who.value = ANONYMOUS
    await nextTick()
    expect(history.entries.value.map(e => e.query)).toEqual(['guest search'])
    expect(readHistory(ALICE, tagCriteria).entries.map(e => e.query)).toEqual(['alice search'])

    who.value = null
    await nextTick()
    expect(history.entries.value).toEqual([])
    history.record('unverified', '')
    expect(readHistory(ALICE, tagCriteria).entries.map(e => e.query)).toEqual(['alice search'])
    expect(readHistory(ANONYMOUS, tagCriteria).entries.map(e => e.query)).toEqual(['guest search'])
  })

  it('fills a list opened while the session was being verified once it is', async () => {
    save(ALICE, [entry('alice search', 1)])
    const { who, history } = setup(null)
    history.show()
    expect(history.shown.value).toBe(false)
    who.value = ALICE
    await nextTick()
    expect([history.shown.value, history.suggestions.value.map(e => e.query)]).toEqual([true, ['alice search']])
  })

  it('shows nothing for an empty history', () => {
    const { history } = setup()
    history.show()
    expect(history.shown.value).toBe(false)
  })

  it('removes one entry and clears the history', () => {
    const { history } = setup()
    history.record('a', '')
    history.record('b', '')
    history.remove(history.entries.value[0])
    expect(readHistory(ALICE, tagCriteria).entries.map(e => e.query)).toEqual(['a'])
    history.clear()
    expect(history.entries.value).toEqual([])
    expect(localStorage.getItem(storageKey('test', ALICE))).toBeNull()
  })

  it('moves with the arrow keys, picks with Enter and closes with Escape', () => {
    const { history, picked } = setup()
    history.record('a', '')
    history.record('b', '')

    // ArrowDown opens the closed list on its first entry.
    expect(history.onKeydown(key('ArrowDown'))).toBe(true)
    expect([history.shown.value, history.activeIndex.value]).toEqual([true, 0])
    history.onKeydown(key('ArrowDown'))
    expect(history.activeIndex.value).toBe(1)
    // Past the last entry the highlight returns to the input, then wraps.
    history.onKeydown(key('ArrowDown'))
    expect(history.activeIndex.value).toBe(-1)
    history.onKeydown(key('ArrowUp'))
    expect(history.activeIndex.value).toBe(1)

    const enter = key('Enter')
    expect(history.onKeydown(enter)).toBe(true)
    expect(enter.defaultPrevented).toBe(true)
    expect(picked.map(e => e.query)).toEqual(['a'])
    expect(history.shown.value).toBe(false)

    history.show()
    const escape = key('Escape')
    expect(history.onKeydown(escape)).toBe(true)
    expect(escape.defaultPrevented).toBe(true)
    expect(history.shown.value).toBe(false)
  })

  it('leaves Enter to the input when no entry is highlighted', () => {
    const { history, picked } = setup()
    history.record('a', '')
    history.show()
    expect(history.onKeydown(key('Enter'))).toBe(false)
    expect(picked).toEqual([])
  })

  it('removes the highlighted entry with Shift+Delete', () => {
    const { history } = setup()
    history.record('a', '')
    history.record('b', '')
    history.onKeydown(key('ArrowDown'))
    expect(history.onKeydown(key('Delete', { shiftKey: true }))).toBe(true)
    expect(history.entries.value.map(e => e.query)).toEqual(['a'])
  })

  it('narrows the shown entries to the typed text', async () => {
    const { history, text } = setup()
    history.record('old gazette', '')
    history.record('weather', '')
    history.show()
    text.value = 'GAZ'
    await nextTick()
    expect(history.suggestions.value.map(e => e.query)).toEqual(['old gazette'])
    text.value = 'nothing like it'
    await nextTick()
    expect(history.shown.value).toBe(false)
  })
})

describe('SearchHistoryDropdown', () => {
  const items = [
    { key: '1', query: '<b>bold</b> query', detail: 'Language: Czech' },
    { key: '2', query: 'second', detail: '' }
  ]

  function mountDropdown (activeIndex = -1) {
    return mount(SearchHistoryDropdown, {
      props: { items, activeIndex, listId: 'history' },
      global: { plugins: [[Quasar, {}]] }
    })
  }

  it('asks for a reload instead of listing a history of a newer format', () => {
    const wrapper = mount(SearchHistoryDropdown, {
      props: { items: [], activeIndex: -1, listId: 'history', newerFormat: true, note: 'Loading search options' },
      global: { plugins: [[Quasar, {}]] }
    })
    expect(wrapper.get('[data-testid="search-history-reload"]').text()).toContain('Reload the page')
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="search-history-clear"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="search-history-note"]').exists()).toBe(false)
  })

  it('lists entries as plain text with their criteria and marks the highlighted one', () => {
    const wrapper = mountDropdown(1)
    const options = wrapper.findAll('[role="option"]')
    expect(options).toHaveLength(2)
    expect(options[0].text()).toContain('<b>bold</b> query')
    expect(options[0].find('b').exists()).toBe(false)
    expect(options[0].text()).toContain('Language: Czech')
    expect(options.map(o => o.attributes('aria-selected'))).toEqual(['false', 'true'])
    expect(options[1].attributes('id')).toBe('history-option-1')
  })

  it('emits choose, remove and clear', async () => {
    const wrapper = mountDropdown()
    await wrapper.findAll('[role="option"]')[1].trigger('click')
    await wrapper.findAll('[data-testid="search-history-remove"]')[0].trigger('click')
    await wrapper.find('[data-testid="search-history-clear"]').trigger('click')
    expect(wrapper.emitted('choose')).toEqual([[1]])
    expect(wrapper.emitted('remove')).toEqual([[0]])
    expect(wrapper.emitted('clear')).toEqual([[]])
  })

  it('keeps the focus in the input when its buttons are pressed', async () => {
    const input = document.createElement('input')
    document.body.appendChild(input)
    const wrapper = mount(SearchHistoryDropdown, {
      props: { items, activeIndex: -1, listId: 'history' },
      global: { plugins: [[Quasar, {}]] },
      attachTo: document.body
    })
    for (const selector of ['[data-testid="search-history-remove"]', '[data-testid="search-history-clear"]']) {
      input.focus()
      const button = wrapper.find(selector)
      await button.trigger('mousedown')
      document.dispatchEvent(new MouseEvent('mouseup'))
      await button.trigger('click')
      expect(document.activeElement, selector).toBe(input)
    }
    wrapper.unmount()
    input.remove()
  })

  it('keeps the focus in the input while an entry is pressed', async () => {
    const wrapper = mountDropdown()
    const press = new MouseEvent('mousedown', { bubbles: true, cancelable: true })
    wrapper.findAll('[role="option"]')[0].element.dispatchEvent(press)
    expect(press.defaultPrevented).toBe(true)
  })
})

describe('Search page criteria', () => {
  const filters = [
    { id: 'language', type: 'nominal', values: [{ userForm: 'Czech', backendForm: 'ces' }, { userForm: 'German', backendForm: 'deu' }] },
    { id: 'year', type: 'interval', minValue: 1800, maxValue: 2000 }
  ] as unknown as SearchFilter[]

  const options: SearchOptions = {
    filters,
    vectors: [{ id: 'fake-default', name: 'Fake default' }, { id: 'fake-small', name: 'Fake small' }] as SearchOptions['vectors'],
    collections: [{ id: 'c1', name: 'My letters' }]
  }

  const criteria = (overrides: Partial<SearchHistoryCriteria> = {}): SearchHistoryCriteria => ({
    type: SearchType.hybrid,
    vector: 'fake-small',
    userCollectionId: 'c1',
    filters: [{ id: 'year', minValue: 1900, maxValue: 1950 }, { id: 'language', values: ['deu', 'ces'] }],
    ...overrides
  })

  it('keeps the criteria of a request but not its generated titles or summaries', () => {
    const fromRequest = criteriaOfRequest({
      query: 'gazette',
      type: SearchType.hybrid,
      vector: 'fake-small',
      userCollectionId: 'c1',
      searchTitleGenerate: true,
      searchSummaryGenerate: true,
      searchResultsSummaryGenerate: true,
      tagUuids: [],
      positive: true,
      automatic: true,
      filters: [{ id: 'year', minValue: 1900, maxValue: 1950 }, { id: 'language', values: ['deu', 'ces'] }]
    })
    expect(fromRequest).toEqual({
      type: SearchType.hybrid,
      vector: 'fake-small',
      userCollectionId: 'c1',
      filters: [{ id: 'language', values: ['ces', 'deu'] }, { id: 'year', minValue: 1900, maxValue: 1950 }]
    })
    expect(Object.keys(fromRequest).sort()).toEqual(['filters', 'type', 'userCollectionId', 'vector'])
  })

  it('treats the same filters in another order as the same search', () => {
    const reordered = criteria({ filters: [{ id: 'language', values: ['ces', 'deu'] }, { id: 'year', minValue: 1900, maxValue: 1950 }] })
    expect(searchHistoryCriteria.key(reordered)).toBe(searchHistoryCriteria.key(criteria()))
    expect(searchHistoryCriteria.key(criteria({ vector: null }))).not.toBe(searchHistoryCriteria.key(criteria()))
  })

  it('validates stored criteria', () => {
    const parse = (raw: unknown) => searchHistoryCriteria.parse(raw, SEARCH_CRITERIA_VERSION)
    expect(parse(JSON.parse(JSON.stringify(criteria())))).toEqual(criteria())
    const invalid = [
      null,
      'hybrid',
      { ...criteria(), type: 'magic' },
      { ...criteria(), vector: 3 },
      { ...criteria(), userCollectionId: '' },
      { ...criteria(), userCollectionId: undefined },
      { ...criteria(), filters: 'year' },
      { ...criteria(), filters: [{ id: 'year', minValue: 1950, maxValue: 1900 }] },
      { ...criteria(), filters: [{ id: 'year', minValue: '1900', maxValue: 1950 }] },
      { ...criteria(), filters: [{ id: 'language', values: [1] }] },
      { ...criteria(), filters: [{ id: 'language', values: [] }] },
      { ...criteria(), filters: [{ id: 'language', values: ['ces'] }, { id: 'language', values: ['deu'] }] }
    ]
    for (const raw of invalid) expect(parse(raw)).toBeNull()
  })

  it('restores available criteria and resets the other filters', () => {
    const restored = restoreSearch(criteria({ filters: [{ id: 'language', values: ['deu'] }] }), options)
    expect(restored).toEqual({
      type: SearchType.hybrid,
      vector: 'fake-small',
      userCollectionId: 'c1',
      filterValues: { language: ['deu'], year: { min: 1800, max: 2000 } },
      dropped: []
    })
  })

  it('leaves out and names criteria that are no longer available', () => {
    const restored = restoreSearch(criteria({
      vector: 'retired-model',
      userCollectionId: 'lost-access',
      filters: [
        { id: 'language', values: ['ces', 'xxx'] },
        { id: 'year', minValue: 2100, maxValue: 2200 },
        { id: 'removed_filter', values: ['a'] }
      ]
    }), options)
    expect(restored.userCollectionId).toBeNull()
    expect(restored.vector).toBeNull()
    expect(restored.filterValues).toEqual({ language: ['ces'], year: { min: 1800, max: 2000 } })
    expect(restored.dropped).toEqual(['Collection', 'Embedding: retired-model', 'Language: xxx', 'Year: 2100-2200', 'Removed Filter'])
  })

  it('limits a stored range to the current bounds', () => {
    const restored = restoreSearch(criteria({ filters: [{ id: 'year', minValue: 1700, maxValue: 1850 }] }), options)
    expect(restored.filterValues.year).toEqual({ min: 1800, max: 1850 })
    expect(restored.dropped).toEqual([])
  })

  it('describes criteria with current names', () => {
    expect(describeCriteria(criteria(), options)).toBe('My letters · Embedding: Fake small · Year: 1900-1950 · Language: German, Czech')
    expect(describeCriteria(criteria({ userCollectionId: 'gone', vector: null, filters: [] }), options)).toBe('Unavailable collection')
    expect(describeCriteria(criteria({ userCollectionId: null, vector: null, filters: [] }), options)).toBe('')
  })
})
