import { describe, expect, it } from 'vitest'
import type { SearchFilter } from 'src/generated/api'
import { classificationChart, classificationFilters, dimensionOptions, WITHOUT_VALUE_LABEL } from 'src/features/user_collections/passageCharts'

// The rows and options of a collection's included-passage charts (#807).

const nominal = (targetProperty: string, name = '', values = [{ backendForm: 'a', userForm: 'A' }]): SearchFilter =>
  ({ id: targetProperty, name, type: 'nominal', description: '', targetProperty, values })

describe('the classifications offered', () => {
  it('are the configured nominal filters on a chunk classification, subject_domain first, each once (from its last filter)', () => {
    const options = dimensionOptions([
      nominal('style', 'Style'),
      { ...nominal('complexity'), values: [] }, // no values: not configured for the chunk filters
      nominal('language', 'Language'), // the chunk language, not a classification
      nominal('library', 'Library'), // a document property
      { id: 'y', name: 'Year', type: 'interval', description: '', targetProperty: 'yearIssued' },
      nominal('subject_domain'), // no name: humanized
      nominal('style', 'Style again')
    ])

    expect(options).toEqual([{ value: 'subject_domain', label: 'Subject Domain' }, { value: 'style', label: 'Style again' }])
  })

  it('take a classification configured twice from its last filter, as the backend does', () => {
    const filters = [nominal('style', 'Style'), nominal('subject_domain', 'Subject'), nominal('style', 'Style (full)', [{ backendForm: 'b', userForm: 'B' }])]

    expect(dimensionOptions(filters)).toEqual([{ value: 'subject_domain', label: 'Subject' }, { value: 'style', label: 'Style (full)' }])
    expect(classificationFilters(filters).get('style')!.values).toEqual([{ backendForm: 'b', userForm: 'B' }])
  })

  it('keep the filters\' order without subject_domain', () => {
    expect(dimensionOptions([nominal('style'), nominal('complexity')]).map(o => o.value)).toEqual(['style', 'complexity'])
  })
})

describe('the rows of a classification', () => {
  it('are the values some passage holds, then "Without a value"; the configured values are counted', () => {
    const chart = classificationChart({
      dimension: 'style',
      available: true,
      values: [{ value: 'a', count: 2, configured: true }, { value: 'b', count: 0, configured: true },
        { value: 'raw_value', count: 1, configured: false }],
      withoutValueCount: 0,
      withoutValueApproximate: true
    }, nominal('style', 'Style', [{ backendForm: 'a', userForm: 'Value A' }]))

    expect(chart!.rows.map(r => [r.label, r.count, r.kind])).toEqual(
      [['Value A', 2, 'value'], ['raw_value (not configured)', 1, 'value'], [WITHOUT_VALUE_LABEL, 0, 'unknown']])
    expect([chart!.occurring, chart!.configured, chart!.approximate]).toEqual([1, 2, true])
  })

  it('have distinct labels, so values never merge into one bar', () => {
    // "Formal" outside the vocabulary next to "formal" labelled "Formal"; two values with one display name.
    const chart = classificationChart({
      dimension: 'style',
      available: true,
      values: [{ value: 'formal', count: 2, configured: true }, { value: 'formal_x', count: 1, configured: true },
        { value: 'Formal', count: 1, configured: false }],
      withoutValueCount: 0
    }, nominal('style', 'Style', [{ backendForm: 'formal', userForm: 'Formal' }, { backendForm: 'formal_x', userForm: 'Formal' }]))

    expect(chart!.rows.map(r => r.label)).toEqual(
      ['Formal (formal)', 'Formal (formal_x)', 'Formal (not configured)', WITHOUT_VALUE_LABEL])
  })

  it('are none for a classification the store does not record', () => {
    expect(classificationChart({ dimension: 'style', available: false, unavailableReason: 'missing_property' }, undefined)).toBeNull()
  })
})
