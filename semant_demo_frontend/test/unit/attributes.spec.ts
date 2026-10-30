import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { Cardinality, ResponseError, ValueKind, type Attribute, type AttributeValue } from 'src/generated/api'
import { endSession } from 'src/shared/api'
import { AttributeWriteError, useAttributesStore } from 'src/features/attributes/attributesStore'
import { attributesOfTag, orderedValues, tagNames, tagScope, valueName } from 'src/features/attributes/attributeForm'
import { matchParts, searchAttributes } from 'src/features/attributes/attributeSearch'

// Attribute definitions of a collection (#331): answers of a collection, a reload or a
// session left meanwhile are dropped, an older answer never replaces a newer attribute, a
// refused write keeps the backend's message, and Unknown / Not applicable are withdrawn by
// retiring and offered again by restoring the same value (#506). The list's search (#506)
// puts matches first and never shows what Show retired hides, but counts it.

type Deferred = { resolve: (value: unknown) => void, reject: (e: unknown) => void }
const pending = new Map<string, Deferred[]>()
function request<T> (key: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    pending.set(key, [...(pending.get(key) ?? []), { resolve: resolve as (v: unknown) => void, reject }])
  })
}
function next (key: string): Deferred {
  const d = pending.get(key)?.shift()
  if (!d) throw new Error(`no pending request ${key}`)
  return d
}
const settle = () => new Promise(resolve => setTimeout(resolve, 0))
// The value writes sent, with what they asked.
const sent: unknown[][] = []

vi.mock('src/features/attributes/useAttributesRepository', () => ({
  useAttributesRepository: () => ({
    getAll: (collectionId: string) => request(`list:${collectionId}`),
    create: (collectionId: string) => request(`create:${collectionId}`),
    update: (collectionId: string, attributeId: string) => request(`update:${attributeId}`),
    addValue: (collectionId: string, attributeId: string, value: unknown) => {
      sent.push(['addValue', attributeId, value])
      return request(`addValue:${attributeId}`)
    },
    updateValue: (collectionId: string, attributeId: string, valueId: string, patch: unknown) => {
      sent.push(['updateValue', valueId, patch])
      return request(`updateValue:${valueId}`)
    }
  })
}))

const attribute = (id: string, name: string, revision = 1, extra: Partial<Attribute> = {}): Attribute =>
  ({ id, name, cardinality: Cardinality.single, revision, values: [], tagIds: [], ...extra })

const refused = (status: number, detail: string) => new ResponseError(
  new Response(JSON.stringify({ detail }), { status, headers: { 'Content-Type': 'application/json' } }))

describe('attributes store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    pending.clear()
    sent.length = 0
  })

  it('lists by name and drops the answer of a collection left meanwhile', async () => {
    const store = useAttributesStore()
    const first = store.load('c1')
    const second = store.load('c2')
    next('list:c1').resolve([attribute('a1', 'topic')])
    next('list:c2').resolve([attribute('a3', 'topic'), attribute('a2', 'Speaker')])
    await Promise.all([first, second])
    expect(store.attributes.map(a => a.id)).toEqual(['a2', 'a3'])
    expect(store.loading).toBe(false)
  })

  it('never lets an older answer replace a newer attribute', async () => {
    const store = useAttributesStore()
    const load = store.load('c1')
    next('list:c1').resolve([attribute('a1', 'speaker', 1)])
    await load

    const retire = store.updateAttribute('c1', 'a1', { retired: true })
    const rename = store.updateAttribute('c1', 'a1', { name: 'speaker type' })
    next('update:a1').resolve(attribute('a1', 'speaker', 2, { retired: true }))
    await retire
    // The rename answers with revision 3; then a reload that started before it answers with 2.
    const reload = store.load('c1')
    next('update:a1').resolve(attribute('a1', 'speaker type', 3, { retired: true }))
    await rename
    next('list:c1').resolve([attribute('a1', 'speaker', 2, { retired: true })])
    await reload
    expect(store.attributes).toEqual([attribute('a1', 'speaker type', 3, { retired: true })])
  })

  it('keeps an attribute created after a list was sent that the list does not have', async () => {
    const store = useAttributesStore()
    const first = store.load('c1')
    next('list:c1').resolve([attribute('a1', 'speaker')])
    await first
    const reload = store.load('c1')
    const created = store.createAttribute('c1', { name: 'topic' })
    next('create:c1').resolve(attribute('a2', 'topic'))
    await created
    next('list:c1').resolve([attribute('a1', 'speaker')])
    await reload
    expect(store.attributes.map(a => a.id)).toEqual(['a1', 'a2'])

    // A list sent after the creation answered is complete: it decides on its own.
    const later = store.load('c1')
    next('list:c1').resolve([attribute('a1', 'speaker')])
    await later
    expect(store.attributes.map(a => a.id)).toEqual(['a1'])
  })

  it('throws the backend message and status of a refused write and changes nothing', async () => {
    const store = useAttributesStore()
    const load = store.load('c1')
    next('list:c1').resolve([attribute('a1', 'speaker')])
    await load
    const narrowing = store.updateAttribute('c1', 'a1', { tagIds: ['t2'] })
    const message = '3 annotations with values of this attribute have a tag outside the new applicable tags; change or remove those values first.'
    next('update:a1').reject(refused(409, message))
    const error = await narrowing.catch((e: unknown) => e)
    expect(error).toBeInstanceOf(AttributeWriteError)
    expect(error).toMatchObject({ status: 409, message })
    expect(store.attributes).toEqual([attribute('a1', 'speaker')])

    const lost = store.updateValue('c1', 'a1', 'v1', { label: 'x' })
    next('updateValue:v1').reject(new TypeError('Failed to fetch'))
    await expect(lost).rejects.toMatchObject({ status: null, message: 'The value could not be saved.' })
  })

  it('applies a write only in the collection and session it was made in', async () => {
    const store = useAttributesStore()
    const load = store.load('c1')
    next('list:c1').resolve([])
    await load
    const created = store.createAttribute('c1', { name: 'speaker' })
    const switched = store.load('c2')
    next('create:c1').resolve(attribute('a1', 'speaker'))
    // The caller still gets the answer (the dialog closes), but c2 does not list it.
    expect(await created).toMatchObject({ id: 'a1' })
    next('list:c2').resolve([])
    await switched
    expect(store.attributes).toEqual([])

    const signedOut = store.addValue('c2', 'a9', { label: 'x' })
    endSession()
    store.clear()
    next('addValue:a9').resolve(attribute('a9', 'other'))
    await signedOut
    await settle()
    expect(store.attributes).toEqual([])
  })

  it('a value write replaces the whole attribute with its values', async () => {
    const store = useAttributesStore()
    const load = store.load('c1')
    next('list:c1').resolve([attribute('a1', 'speaker')])
    await load
    const added = store.addValue('c1', 'a1', { label: 'politician' })
    next('addValue:a1').resolve(attribute('a1', 'speaker', 2, { values: [{ id: 'v1', label: 'politician' }] }))
    await added
    expect(store.attributes[0]!.values).toEqual([{ id: 'v1', label: 'politician' }])
  })
})

describe('Unknown and Not applicable', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    pending.clear()
    sent.length = 0
  })

  const unknown = (retired: boolean): AttributeValue => ({ id: 'u1', label: 'Unknown', kind: ValueKind.unknown, retired })

  it('adds the special value with its fixed label when the attribute never had one', async () => {
    const store = useAttributesStore()
    const added = store.setSpecialValue('c1', attribute('a1', 'speaker'), ValueKind.notApplicable, true)
    next('addValue:a1').resolve(attribute('a1', 'speaker', 2))
    await added
    expect(sent).toEqual([['addValue', 'a1', { label: 'Not applicable', kind: ValueKind.notApplicable }]])
  })

  it('withdraws by retiring and offers again by restoring the same value, never a second one', async () => {
    const store = useAttributesStore()
    const withdrawn = store.setSpecialValue('c1', attribute('a1', 'speaker', 1, { values: [unknown(false)] }), ValueKind.unknown, false)
    next('updateValue:u1').resolve(attribute('a1', 'speaker', 2, { values: [unknown(true)] }))
    await withdrawn
    const offered = store.setSpecialValue('c1', attribute('a1', 'speaker', 2, { values: [unknown(true)] }), ValueKind.unknown, true)
    next('updateValue:u1').resolve(attribute('a1', 'speaker', 3, { values: [unknown(false)] }))
    await offered
    expect(sent).toEqual([['updateValue', 'u1', { retired: true }], ['updateValue', 'u1', { retired: false }]])
  })

  it('writes nothing when the attribute is already as asked', async () => {
    const store = useAttributesStore()
    const current = attribute('a1', 'speaker', 1, { values: [unknown(false)] })
    expect(await store.setSpecialValue('c1', current, ValueKind.unknown, true)).toBe(current)
    expect(await store.setSpecialValue('c1', attribute('a1', 'speaker'), ValueKind.unknown, false)).toMatchObject({ id: 'a1' })
    expect(sent).toEqual([])
  })
})

describe('attribute form helpers', () => {
  const tags = [{ id: 't1', name: 'Person' }, { id: 't2', name: 'Place' }] as never

  it('lists ordinary values before the special ones, named by their kind', () => {
    const values: AttributeValue[] = [
      { id: 'u', label: 'not known', kind: ValueKind.unknown }, { id: 'p', label: 'politician' }, { id: 'j', label: 'journalist' }
    ]
    expect(orderedValues({ values }).map(valueName)).toEqual(['politician', 'journalist', 'Unknown'])
  })

  it('names the applicable tags in collection order and skips unknown ids', () => {
    const tags = [{ id: 't1', name: 'Person' }, { id: 't2', name: 'Place' }] as never
    expect(tagNames({ tagIds: ['t2', 'gone', 't1'] }, tags)).toEqual(['Person', 'Place'])
  })

  it('says which tags an attribute applies to only once the tags are known, counting deleted ones', () => {
    expect(tagScope({ tagIds: [] }, [], 'loading')).toEqual({ kind: 'all' })
    // Not "only deleted tags" while the tags have not arrived, or could not be loaded.
    expect(tagScope({ tagIds: ['t1'] }, [], 'loading')).toEqual({ kind: 'loading' })
    expect(tagScope({ tagIds: ['t1'] }, [], 'failed')).toEqual({ kind: 'failed' })
    expect(tagScope({ tagIds: ['gone', 't2'] }, tags, 'ready')).toEqual({ kind: 'selected', names: ['Place'], deleted: 1 })
    expect(tagScope({ tagIds: ['gone'] }, tags, 'ready')).toEqual({ kind: 'selected', names: [], deleted: 1 })
  })

  it('gives a tag the current attributes that name it, then those for all tags', () => {
    const attributes = [
      attribute('a1', 'Mood', 1, { tagIds: [] }),
      attribute('a2', 'Speaker', 1, { tagIds: ['t1'] }),
      attribute('a3', 'Stance', 1, { tagIds: ['t1'], retired: true }),
      attribute('a4', 'Topic', 1, { tagIds: ['t2'] })
    ]
    expect(attributesOfTag(attributes, 't1').map(({ attribute, allTags }) => [attribute.name, allTags]))
      .toEqual([['Speaker', false], ['Mood', true]])
  })
})

describe('attribute search', () => {
  const value = (id: string, label: string, extra: Partial<AttributeValue> = {}): AttributeValue => ({ id, label, ...extra })
  const topic = attribute('a1', 'Topic', 1, {
    values: [value('v1', 'economy'), value('v2', 'elections'), value('v3', 'health'), value('v4', 'electoral law', { retired: true })]
  })
  const speaker = attribute('a2', 'Speaker', 1, { values: [value('v5', 'politician'), value('v6', 'n/k', { kind: ValueKind.unknown })] })
  const retired = attribute('a3', 'Election year', 1, { retired: true, values: [value('v7', '1920')] })
  const labels = (search: ReturnType<typeof searchAttributes>) =>
    search.shown.map(s => [s.attribute.name, s.values.map(v => v.label)])

  it('marks each match, ignoring case', () => {
    expect(matchParts('Elections and electoral law', 'ELEC')).toEqual([
      { text: 'Elec', match: true }, { text: 'tions and ', match: false }, { text: 'elec', match: true },
      { text: 'toral law', match: false }
    ])
    expect(matchParts('economy', '  ')).toEqual([{ text: 'economy', match: false }])
  })

  it('shows every attribute without a search, retired ones only with Show retired', () => {
    expect(labels(searchAttributes([topic, speaker, retired], '', false))).toEqual([
      ['Topic', ['economy', 'elections', 'health']], ['Speaker', ['politician', 'n/k']]
    ])
    expect(searchAttributes([topic, speaker, retired], '', true).shown).toHaveLength(3)
  })

  it('puts matching values first and keeps a name match in its ordinary order', () => {
    expect(labels(searchAttributes([topic, speaker], 'heal', true))).toEqual([['Topic', ['health', 'economy', 'elections', 'electoral law']]])
    expect(labels(searchAttributes([topic, speaker], 'speak', true))).toEqual([['Speaker', ['politician', 'n/k']]])
    // A special value is found by its kind's name.
    expect(labels(searchAttributes([topic, speaker], 'unknown', true))).toEqual([['Speaker', ['n/k', 'politician']]])
  })

  it('counts the matches Show retired hides instead of showing them', () => {
    const search = searchAttributes([topic, speaker, retired], 'elect', false)
    // elections is shown; electoral law (retired value) and Election year (retired attribute) are not.
    expect(labels(search)).toEqual([['Topic', ['elections', 'economy', 'health']]])
    expect(search.hiddenMatches).toBe(2)

    const onlyHidden = searchAttributes([topic, retired], 'electoral', false)
    expect([onlyHidden.shown, onlyHidden.hiddenMatches]).toEqual([[], 1])
    expect(searchAttributes([topic, retired], 'elect', true).hiddenMatches).toBe(0)
  })
})
