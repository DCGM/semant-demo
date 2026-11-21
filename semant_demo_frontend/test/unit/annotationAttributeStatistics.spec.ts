import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { Quasar } from 'quasar'

import { Cardinality, SpanType, type AnnotationFacets, type Attribute, type Facet } from 'src/generated/api'
import { defaultFilters } from 'src/features/annotations/concordance/concordanceStore'
import AnnotationStatisticsPanel from 'src/features/annotations/statistics/AnnotationStatisticsPanel.vue'
import { applicableTags, attributeDistribution, attributeDrillChange, statisticsRequest } from 'src/features/annotations/statistics/statistics'

// Accepted attribute-value distributions (#819): applicable-only counts, annotations with a value
// beside assignments, Not assigned, retained inapplicable values only on request, and drill-downs
// that list exactly the counted annotations (status and applicable tags, not the stored filter alone).

const attribute = (extra: Partial<Attribute> = {}): Attribute => ({
  id: 'a1',
  name: 'Speaker type',
  cardinality: Cardinality.multi,
  allTags: false,
  tagIds: ['t1'],
  retired: false,
  values: [{ id: 'red', label: 'Red' }, { id: 'green', label: 'Green' }, { id: 'old', label: 'Old', retired: true }],
  ...extra
} as Attribute)

/** 10 eligible annotations: 6 with a value (4 red, 3 green, one both), 4 without; 2 red values retained on other tags. */
const facet = (extra: Partial<Facet> = {}): Facet => ({
  facet: 'attribute:a1',
  values: [{ value: 'red', count: 6, inapplicable: 2 }, { value: 'green', count: 3, inapplicable: 0 }, { value: 'old', count: 0, inapplicable: 0 }],
  missing: 12,
  total: 20,
  eligible: 10,
  withValue: 6,
  assignments: 7,
  ...extra
} as Facet)

describe('accepted attribute-value distributions', () => {
  it('asks for the attribute facets with the statistics', () => {
    expect(statisticsRequest(defaultFilters(), ['a1']).facets).toEqual(
      ['type', 'tag', 'year', 'document', 'library', 'language', 'attribute:a1'])
  })

  it('counts applicable assignments and keeps annotations with a value, assignments and Not assigned apart', () => {
    const d = attributeDistribution(facet(), attribute(), defaultFilters(), true, false)!
    expect(d.rows.map(r => [r.label, r.count])).toEqual([['Red', 4], ['Green', 3], ['Not assigned', 4]]) // retired value without annotations omitted
    expect([d.eligible, d.withValue, d.assignments, d.missing]).toEqual([10, 6, 7, 4])
    expect(d.assignments).toBeGreaterThan(d.withValue) // value totals may exceed the annotations
    expect(d.rows[0].share).toBeCloseTo(0.4)
    expect(d.retained).toBe(2)
  })

  it('counts retained inapplicable values only when asked, and says how many', () => {
    const d = attributeDistribution(facet(), attribute(), defaultFilters(), true, true)!
    expect(d.rows.find(r => r.key === 'red')!.count).toBe(6)
    expect(d.retained).toBe(2)
  })

  it('has no distribution without server statistics', () => {
    expect(attributeDistribution(null, attribute(), defaultFilters(), true, false)).toBeNull()
    expect(attributeDistribution(facet({ eligible: null }), attribute(), defaultFilters(), true, false)).toBeNull()
  })

  it('drills into confirmed annotations of the applicable tags, not the stored filter alone', () => {
    const f = { ...defaultFilters(), attributeValues: ['b1:x'], attributeUnassigned: ['b2'] }
    expect(attributeDrillChange(attribute(), 'red', f)).toEqual({
      types: [SpanType.pos], tagIds: ['t1'], attributeValues: ['b1:x', 'a1:red'], attributeUnassigned: ['b2']
    })
    expect(attributeDrillChange(attribute(), null, f)).toEqual({
      types: [SpanType.pos], tagIds: ['t1'], attributeValues: ['b1:x'], attributeUnassigned: ['b2', 'a1']
    })
    // the stored-holders view lists a different population: any tag
    expect(attributeDrillChange(attribute(), 'red', f, true)).toMatchObject({ tagIds: [], types: [SpanType.pos] })
  })

  it('applies the query\'s own tag filter and an all-tags attribute', () => {
    expect(applicableTags(attribute(), { ...defaultFilters(), tagIds: ['t1', 't9'] })).toEqual(['t1'])
    expect(applicableTags(attribute(), { ...defaultFilters(), tagIds: ['t9'] })).toBeNull()
    expect(applicableTags(attribute({ allTags: true }), { ...defaultFilters(), tagIds: ['t9'] })).toEqual(['t9'])
    expect(attributeDrillChange(attribute(), 'red', { ...defaultFilters(), tagIds: ['t9'] })).toBeNull()
  })

  it('offers no drill-down the query\'s own filter on the attribute contradicts', () => {
    const own = { ...defaultFilters(), attributeValues: ['a1:red'] }
    expect(attributeDrillChange(attribute(), 'green', own)).toBeNull() // red AND green is no single filter
    expect(attributeDrillChange(attribute(), 'red', own)).not.toBeNull()
    expect(attributeDrillChange(attribute(), null, own)).toBeNull()
    expect(attributeDistribution(facet(), attribute(), defaultFilters(), false, false)!.rows.every(r => r.drill === null)).toBe(true)
  })
})

describe('the attribute section of the statistics view', () => {
  const statistics = (facets: Facet[]): AnnotationFacets => ({ population: 'filtered', selfExclusion: false, facets } as AnnotationFacets)
  const base = [
    { facet: 'type', values: [{ value: 'pos', count: 20 }], missing: 0, total: 20 },
    { facet: 'tag', values: [{ value: 't1', count: 20 }], missing: 0, total: 20 }
  ] as Facet[]

  function mountPanel (facets: Facet[]) {
    return mount(AnnotationStatisticsPanel, {
      props: { filters: defaultFilters(), statistics: statistics([...base, ...facets]), error: null, tags: [], documents: [], attributes: [attribute()], dimension: null },
      global: { plugins: [Quasar] }
    })
  }

  it('shows applicable counts with annotations and assignments, and explains multi-valued totals', () => {
    const wrapper = mountPanel([facet()])
    const card = wrapper.get('[data-testid="statistics-attribute-a1"]')
    expect(card.get('[data-testid="statistics-attribute-summary"]').text()).toContain('6 of 10 confirmed annotations with a value · 7 assignments')
    expect(card.text()).toContain('counts once under each of its values')
    expect(card.get('[data-testid="statistics-attribute-a1-values-show-red"]').text()).toBe('Red')
    expect(card.text()).not.toContain('retained')
  })

  it('labels retained values as a different population only after asking for them', async () => {
    const wrapper = mountPanel([facet()])
    await wrapper.get('[data-testid="statistics-include-retained"]').trigger('click')
    expect(wrapper.get('[data-testid="statistics-attribute-a1"]').text()).toContain('a different population')
  })

  it('emits the narrowed query when a value is chosen', async () => {
    const wrapper = mountPanel([facet()])
    await wrapper.get('[data-testid="statistics-attribute-a1-values-show-red"]').trigger('click')
    expect(wrapper.emitted('drill')![0][0]).toMatchObject({ types: ['pos'], tagIds: ['t1'], attributeValues: ['a1:red'] })
  })

  it('says so when the attribute applies to no matching confirmed annotation', () => {
    const wrapper = mountPanel([facet({ eligible: 0, withValue: 0, assignments: 0, values: [] })])
    expect(wrapper.get('[data-testid="statistics-attribute-a1"]').text()).toContain('No confirmed annotation of a tag this attribute applies to')
  })
})
