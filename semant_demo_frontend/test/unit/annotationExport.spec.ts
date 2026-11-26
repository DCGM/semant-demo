import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Quasar } from 'quasar'

import AnnotationExportDialog from 'src/features/annotations/concordance/AnnotationExportDialog.vue'
import {
  defaultExportOptions, downloadExport, jsonCompletion, exportFailure, exportFilterSummary, exportRequest, InterruptedDownload, resultText
} from 'src/features/annotations/concordance/annotationExport'
import { defaultFilters, type ConcordanceFilters } from 'src/features/annotations/concordance/concordanceStore'
import { AnnotationExportScope, CsvDelimiter, ExportFormat, RetrievalMode, SpanType } from 'src/generated/api'

// CSV export of the workspace (#719): the request names exactly the selection, the current
// filters or the chosen statuses; the file is saved only once it arrived whole; the dialog states
// the scope and count, offers only exportable scopes and says what was saved.

const filters = (change: Partial<ConcordanceFilters> = {}): ConcordanceFilters => ({ ...defaultFilters(), ...change })
const CSV_HEADERS = {
  'Content-Type': 'text/csv; charset=utf-8',
  'Content-Disposition': 'attachment; filename="annotations-selection-2026-11-16.csv"',
  'X-Export-Count': '2',
  'X-Export-Missing': '1',
  'X-Export-Scope': 'selection'
}

/** A body that sends its first part, then fails (the server aborted the export). */
function brokenBody (): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start (controller) {
      controller.enqueue(new TextEncoder().encode('﻿annotation_id\r\n'))
      controller.error(new TypeError('network error'))
    }
  })
}

describe('export requests', () => {
  it('sends the selection ids, the current filters or the chosen statuses with the column groups', () => {
    const options = { ...defaultExportOptions(AnnotationExportScope.selection), provenance: true, delimiter: CsvDelimiter.semicolon }
    expect(exportRequest(options, filters(), new Set(['a', 'b']))).toEqual({
      scope: 'selection',
      annotationIds: ['a', 'b'],
      documentMetadata: true,
      chunkMetadata: false,
      provenance: true,
      delimiter: 'semicolon',
      format: 'csv'
    })
    const filtered = exportRequest({ ...options, scope: AnnotationExportScope.filters },
      filters({ tagIds: ['t'], text: ' Brno ', types: [SpanType.neg], documentFilters: { yearMin: 1900 } }), [])
    expect(filtered.filters).toMatchObject({ tagIds: ['t'], q: 'Brno', types: ['neg'], documentFilters: { yearMin: 1900 } })
    expect(filtered.annotationIds).toBeUndefined()
    const all = exportRequest({ ...options, scope: AnnotationExportScope.collection, types: [SpanType.neg] }, filters({ tagIds: ['t'] }), ['a'])
    expect(all).toMatchObject({ scope: 'collection', types: ['neg'] })
    expect(all.filters).toBeUndefined()
  })

  it('asks for JSON with audit and, for a ranked result, its top k', () => {
    const options = { ...defaultExportOptions(AnnotationExportScope.filters), format: ExportFormat.json, audit: true }
    const ranked = exportRequest(options, filters({ mode: RetrievalMode.semantic, k: 50, text: 'x' }), [])
    expect(ranked).toMatchObject({ scope: 'filters', format: 'json', audit: true, ranking: { mode: 'semantic', k: 50 } })
    expect(exportRequest(options, filters(), []).ranking).toBeUndefined()
    expect(exportRequest({ ...options, format: ExportFormat.csv }, filters(), []).audit).toBeUndefined()
  })

  it('reads the closing completion of a JSON file and rejects a file without it', async () => {
    const whole = new Blob(['{"manifest":{},"annotations":[{"a":1}],"completion":{"complete":false,"missing_ids":["x","y"]}}'])
    expect(await jsonCompletion(whole)).toEqual({ complete: false, missingIds: ['x', 'y'] })
    await expect(jsonCompletion(new Blob(['{"manifest":{},"annotations":[{"a":1}']))).rejects.toBeInstanceOf(InterruptedDownload)
  })

  it('names the statuses of the filter scope even when they are the default', () => {
    expect(exportFilterSummary(filters(), [])).toBe('Filters: Status: Confirmed, Proposals.')
    expect(exportFilterSummary(filters({ types: [SpanType.neg] }), [
      { key: 'types', group: 'Status', label: 'Rejected', remove: {} },
      { key: 'tag:t', group: 'Tag', label: 'Osoba', remove: {} }
    ])).toBe('Filters: Status: Rejected · Tag: Osoba.')
  })

  it('describes what was saved, including missing selected annotations', () => {
    expect(resultText({ scope: AnnotationExportScope.selection, count: 2, missing: 1, deleted: 0, filename: 'a.csv' }))
      .toBe('Saved a.csv: 2 annotations (selected annotations). 1 selected annotation no longer exists and was not exported.')
    expect(resultText({ scope: AnnotationExportScope.collection, count: 0, missing: 0, deleted: 0, filename: 'b.csv' }))
      .toBe('Saved b.csv: 0 annotations (all annotations in the collection).')
  })
})

describe('downloading an export', () => {
  const originalFetch = globalThis.fetch
  afterEach(() => { globalThis.fetch = originalFetch })

  it('saves the whole file with the name, count and missing ids the server sent', async () => {
    const fetchMock = vi.fn(async () => new Response('﻿annotation_id\r\na\r\nb\r\n', { headers: CSV_HEADERS }))
    globalThis.fetch = fetchMock as typeof fetch
    const save = vi.fn()
    const result = await downloadExport('col-1', { scope: AnnotationExportScope.selection, annotationIds: ['a', 'b', 'gone'] }, undefined, save)
    expect(result).toEqual({ scope: 'selection', count: 2, missing: 1, deleted: 0, filename: 'annotations-selection-2026-11-16.csv' })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toMatch(/\/api\/user_collections\/col-1\/annotations\/export$/)
    expect(JSON.parse(String(init.body))).toMatchObject({ scope: 'selection', annotation_ids: ['a', 'b', 'gone'] })
    const [blob, name] = save.mock.calls[0] as [Blob, string]
    expect(name).toBe('annotations-selection-2026-11-16.csv')
    expect(await blob.text()).toContain('a\r\nb\r\n')
  })

  it('saves nothing when the file is interrupted and says so', async () => {
    globalThis.fetch = vi.fn(async () => new Response(brokenBody(), { headers: CSV_HEADERS })) as typeof fetch
    const save = vi.fn()
    const failure = await downloadExport('col-1', { scope: AnnotationExportScope.collection, types: [SpanType.pos] }, undefined, save)
      .catch(e => e)
    expect(failure).toBeInstanceOf(InterruptedDownload)
    expect(save).not.toHaveBeenCalled()
    expect(await exportFailure(failure)).toContain('nothing was saved')
  })

  it('reports a refused export with the server reason', async () => {
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({ detail: 'A document has 12000 matching annotations' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } })) as typeof fetch
    const failure = await downloadExport('col-1', { scope: AnnotationExportScope.collection, types: [SpanType.pos] }, undefined, vi.fn())
      .catch(e => e)
    expect(await exportFailure(failure)).toBe('A document has 12000 matching annotations')
  })
})

describe('AnnotationExportDialog', () => {
  const originalFetch = globalThis.fetch
  let bodies: unknown[]
  let clicks: ReturnType<typeof vi.fn>

  beforeEach(() => {
    bodies = []
    clicks = vi.fn()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { clicks(this.download) })
    globalThis.fetch = vi.fn(async (input: Parameters<typeof fetch>[0], init?: RequestInit) => {
      if (String(input).endsWith('/annotations/counts')) {
        return new Response(JSON.stringify({ approved: 5, suggestions: 2, rejected: 3 }), { headers: { 'Content-Type': 'application/json' } })
      }
      bodies.push(JSON.parse(String(init?.body)))
      return new Response('﻿annotation_id\r\n', { headers: { ...CSV_HEADERS, 'X-Export-Count': '7', 'X-Export-Missing': '0', 'X-Export-Scope': 'collection', 'Content-Disposition': 'attachment; filename="annotations-collection.csv"' } })
    }) as typeof fetch
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
  })
  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  const props = {
    modelValue: false,
    collectionId: 'col-1',
    filters: filters(),
    filterSummary: 'Filters: Status: Confirmed, Proposals.',
    selectedIds: new Set<string>(),
    hiddenSelected: 0,
    total: 42,
    ranked: false
  }
  const open = async (change: Partial<typeof props> = {}) => {
    const wrapper = mount(AnnotationExportDialog, { props: { ...props, ...change }, global: { plugins: [[Quasar, {}]] }, attachTo: document.body })
    await wrapper.setProps({ modelValue: true })
    await flushPromises()
    return wrapper
  }
  const byTestId = (id: string) => document.querySelector(`[data-testid="${id}"]`) as HTMLElement | null
  const checked = (id: string) => byTestId(id)?.getAttribute('aria-checked') === 'true'

  it('opens on the selection, flags members outside the filters and shows its count', async () => {
    const wrapper = await open({ selectedIds: new Set(['a', 'b', 'c']), hiddenSelected: 2 })
    expect(checked('export-scope-selection')).toBe(true)
    expect(byTestId('export-scope-selection')?.textContent).toContain('Selected annotations (3)')
    expect(byTestId('export-hidden-selected')?.textContent).toContain('2 of them are not shown by the current filters')
    expect(byTestId('export-target')?.textContent).toContain('Exports 3 selected annotations.')
    wrapper.unmount()
  })

  it('exports a ranked result as its top k and opens on the filter matches', async () => {
    const ranked = await open({ ranked: true, filters: filters({ mode: RetrievalMode.semantic, text: 'x' }) })
    expect(byTestId('export-scope-filters')?.getAttribute('aria-disabled')).not.toBe('true')
    expect(byTestId('export-scope-filters')?.textContent).toContain('Top 42 of the ranked result')
    expect(checked('export-scope-filters')).toBe(true)
    ranked.unmount()
    const lexical = await open()
    expect(checked('export-scope-filters')).toBe(true)
    expect(byTestId('export-scope-filters')?.textContent).toContain('Current filter matches (42)')
    expect(byTestId('export-filter-summary')?.textContent).toContain('Status: Confirmed, Proposals')
    lexical.unmount()
  })

  it('exports the chosen statuses of the whole collection and says what was saved', async () => {
    const wrapper = await open({ ranked: true, total: 0 })
    expect(byTestId('export-status-neg')?.textContent).toContain('Rejected (3)')
    expect(byTestId('export-target')?.textContent).toContain('Exports 10 annotations.')
    byTestId('export-status-auto')?.click()
    await flushPromises()
    expect(byTestId('export-target')?.textContent).toContain('Exports 8 annotations.')
    byTestId('export-provenance')?.click()
    byTestId('export-download')?.click()
    await flushPromises()
    expect(bodies).toEqual([{ scope: 'collection', types: ['pos', 'neg'], document_metadata: true, chunk_metadata: false, provenance: true, delimiter: 'comma', format: 'csv' }])
    expect(clicks).toHaveBeenCalledWith('annotations-collection.csv')
    expect(byTestId('export-result')?.textContent).toContain('Saved annotations-collection.csv: 7 annotations (all annotations in the collection).')
    wrapper.unmount()
  })
})
