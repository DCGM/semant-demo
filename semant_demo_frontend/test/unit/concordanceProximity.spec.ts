import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { QBtn, QBtnToggle, QSelect, Quasar } from 'quasar'

import { DistanceUnit, NearDirection, NearRelation, type Tag } from 'src/generated/api'
import ConcordanceToolbar from 'src/features/annotations/concordance/ConcordanceToolbar.vue'
import {
  annotationFilters, defaultFilters, nearParameters, type ConcordanceFilters
} from 'src/features/annotations/concordance/concordanceStore'
import { concordanceChips, defaultNear, nearRelationText, nearSummary, proximityLabel } from 'src/features/annotations/concordance/filterChips'

// The proximity filter of the annotation workspace (#333): a compact form in More filters, one
// removable chip, the same filter in GET parameters and request bodies, and an honest note on
// what could not be compared.

const tag = (id: string, name: string): Tag => ({ id, name, shorthand: name[0], color: '#111', pictogram: '', definition: '', examples: [] })
const tags: Tag[] = [tag('statement', 'Statement'), tag('criticism', 'Criticism')]
const filters = (change: Partial<ConcordanceFilters>): ConcordanceFilters => ({ ...defaultFilters(), ...change })

describe('proximity filter', () => {
  it('describes the relation as the chip says it', () => {
    expect(nearRelationText(defaultNear(['criticism']))).toBe('within 50 words')
    expect(nearRelationText({ ...defaultNear([]), distance: 10, unit: DistanceUnit.chars, direction: NearDirection.after }))
      .toBe('within 10 characters after')
    expect(nearRelationText({ ...defaultNear([]), relation: NearRelation.overlaps })).toBe('overlapping')
  })

  it('is one removable chip, "Not near" when absent', () => {
    const near = { ...defaultNear(['criticism']), absent: true }
    expect(concordanceChips(filters({ near }), tags, [], [])).toEqual([
      { key: 'near', group: 'Not near', label: 'Criticism within 50 words', remove: { near: null } }
    ])
  })

  it('is sent as near_ parameters and in request bodies, and not at all without it', () => {
    const near = { ...defaultNear(['criticism']), direction: NearDirection.before }
    expect(nearParameters(near)).toEqual({
      nearRelation: 'within',
      nearTagId: ['criticism'],
      nearType: undefined,
      nearAttribute: undefined,
      nearDistance: 50,
      nearUnit: 'words',
      nearDirection: 'before',
      nearAbsent: undefined
    })
    expect(nearParameters(null)).toEqual({})
    expect(annotationFilters(filters({ near })).near).toEqual(near)
    expect(annotationFilters(defaultFilters()).near).toBeUndefined()
  })

  it('reads as one sentence, the negation included', () => {
    const near = defaultNear(['criticism'])
    expect(nearSummary(near, ['Statement'], ['Criticism'])).toBe(
      'Shows Statement annotations that have an annotation tagged Criticism at most 50 words away. ' +
      'Annotations whose position is not known yet are left out.')
    expect(nearSummary({ ...near, absent: true, direction: NearDirection.after, distance: 3 }, [], ['Criticism']))
      .toMatch(/^Shows annotations that have no annotation tagged Criticism starting at most 3 words after it\./)
    expect(nearSummary({ ...near, relation: NearRelation.containedBy }, [], [])).toMatch(/annotation of any tag that contains it\./)
    expect(nearSummary(null, [], [])).toMatch(/^Choose neighbor tags/)
  })

  it('says what could not be compared, and nothing when all was', () => {
    expect(proximityLabel({ unknown: 0, neighborsUnpositioned: 0 })).toBeNull()
    expect(proximityLabel(null)).toBeNull()
    expect(proximityLabel({ unknown: 1, neighborsUnpositioned: 2 }))
      .toBe('Proximity: 1 annotation with unknown positions left out, 2 neighbors with unknown positions not compared')
  })
})

describe('proximity form', () => {
  const mounted: VueWrapper[] = []
  afterEach(() => {
    mounted.splice(0).forEach(w => w.unmount())
    document.body.innerHTML = ''
  })
  const toolbar = async (f: ConcordanceFilters) => {
    const wrapper = mount(ConcordanceToolbar as never, {
      props: { filters: f, tags, documents: [] } as never, global: { plugins: [Quasar] }, attachTo: document.body
    })
    mounted.push(wrapper)
    await wrapper.findAllComponents(QBtn).find(b => b.attributes('data-testid') === 'concordance-more-filters')!.trigger('click')
    await flushPromises()
    return wrapper
  }
  const select = (w: VueWrapper, testid: string) =>
    w.findAllComponents(QSelect).find(s => s.find(`[data-testid="${testid}"]`).exists() || s.attributes('data-testid') === testid)

  it('starts with the neighbor tags and ends when they are cleared', async () => {
    const empty = await toolbar(defaultFilters())
    expect(select(empty, 'concordance-near-placement')).toBeUndefined()
    expect(empty.findComponent(QBtnToggle).exists()).toBe(false)
    select(empty, 'concordance-near-tags')!.vm.$emit('update:modelValue', ['criticism'])
    expect(empty.emitted('change')).toEqual([[{ near: defaultNear(['criticism']) }]])

    const active = await toolbar(filters({ near: defaultNear(['criticism']) }))
    expect(active.text()).toContain('More filters (1)')
    expect(active.find('[data-testid="concordance-near-summary"]').text()).toContain('have an annotation tagged Criticism')
    select(active, 'concordance-near-placement')!.vm.$emit('update:modelValue', 'after')
    active.findComponent(QBtnToggle).vm.$emit('update:modelValue', 'without')
    select(active, 'concordance-near-placement')!.vm.$emit('update:modelValue', 'overlaps')
    select(active, 'concordance-near-tags')!.vm.$emit('update:modelValue', null)
    expect(active.emitted('change')).toEqual([
      [{ near: { ...defaultNear(['criticism']), direction: NearDirection.after } }],
      [{ near: { ...defaultNear(['criticism']), absent: true } }],
      [{ near: { ...defaultNear(['criticism']), relation: NearRelation.overlaps } }],
      [{ near: null }]
    ])
  })

  it('asks for a distance only within a distance', async () => {
    const overlap = await toolbar(filters({ near: { ...defaultNear(['criticism']), relation: NearRelation.overlaps } }))
    expect(select(overlap, 'concordance-near-unit')).toBeUndefined()
    expect(overlap.find('[data-testid="concordance-near-distance"]').exists()).toBe(false)
  })
})
