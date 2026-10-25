import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { Cardinality, ResponseError, type Attribute } from 'src/generated/api'
import { endSession } from 'src/shared/api'
import { AttributeWriteError, useAttributesStore } from 'src/features/attributes/attributesStore'
import { appliesTo, repeatedKinds, tagNames } from 'src/features/attributes/attributeForm'

// Attribute definitions of a collection (#331): answers of a collection, a reload or a
// session left meanwhile are dropped, an older answer never replaces a newer attribute, and a
// refused write keeps the backend's message.

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

vi.mock('src/features/attributes/useAttributesRepository', () => ({
  useAttributesRepository: () => ({
    getAll: (collectionId: string) => request(`list:${collectionId}`),
    create: (collectionId: string) => request(`create:${collectionId}`),
    update: (collectionId: string, attributeId: string) => request(`update:${attributeId}`),
    delete: (collectionId: string, attributeId: string) => request(`delete:${attributeId}`),
    addValue: (collectionId: string, attributeId: string) => request(`addValue:${attributeId}`),
    updateValue: (collectionId: string, attributeId: string, valueId: string) => request(`updateValue:${valueId}`),
    deleteValue: (collectionId: string, attributeId: string, valueId: string) => request(`deleteValue:${valueId}`)
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

  it('keeps a deleted attribute out of a list that was read before the deletion', async () => {
    const store = useAttributesStore()
    const first = store.load('c1')
    next('list:c1').resolve([attribute('a1', 'speaker'), attribute('a2', 'topic')])
    await first
    const reload = store.load('c1')
    const deletion = store.deleteAttribute('c1', 'a1')
    next('delete:a1').resolve(undefined)
    await deletion
    next('list:c1').resolve([attribute('a1', 'speaker'), attribute('a2', 'topic')])
    await reload
    expect(store.attributes.map(a => a.id)).toEqual(['a2'])
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
    const deletion = store.deleteAttribute('c1', 'a1')
    next('delete:a1').reject(refused(409, '3 annotations have values of this attribute; retire it instead of deleting it.'))
    const error = await deletion.catch((e: unknown) => e)
    expect(error).toBeInstanceOf(AttributeWriteError)
    expect(error).toMatchObject({ status: 409, message: '3 annotations have values of this attribute; retire it instead of deleting it.' })
    expect(store.attributes.map(a => a.id)).toEqual(['a1'])

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

describe('attribute form helpers', () => {
  it('finds a repeated Unknown or Not applicable kind, not repeated plain values', () => {
    expect(repeatedKinds(['value', 'value', 'unknown'])).toEqual([])
    expect(repeatedKinds(['unknown', 'not_applicable', 'unknown'])).toEqual(['unknown'])
  })

  it('names the applicable tags in collection order and skips unknown ids', () => {
    const tags = [{ id: 't1', name: 'Person' }, { id: 't2', name: 'Place' }] as never
    expect(tagNames({ tagIds: ['t2', 'gone', 't1'] }, tags)).toEqual(['Person', 'Place'])
  })

  it('says which tags an attribute applies to, without naming deleted ones', () => {
    const tags = [{ id: 't1', name: 'Person' }, { id: 't2', name: 'Place' }] as never
    expect(appliesTo({ tagIds: [] }, tags)).toBe('all tags')
    expect(appliesTo({ tagIds: ['gone', 't2'] }, tags)).toBe('tags Place')
    expect(appliesTo({ tagIds: ['gone'] }, tags)).toBe('only deleted tags')
  })
})
