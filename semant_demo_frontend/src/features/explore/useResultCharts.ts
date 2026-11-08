import { getCurrentScope, onScopeDispose, ref, shallowRef } from 'vue'
import {
  RankedResultsDistributionsRequestModeEnum, SearchType, type CategoryDistribution, type RankedResultsDistributions,
  type ResultMember
} from 'src/generated/api'
import { apiErrorMessage, errorStatus, isAbortError, useApi } from 'src/shared/api'
import { languageLabel, libraryLabel } from 'src/features/analytics/corpusOverview'
import { SLOW_AFTER_MS } from 'src/features/analytics/useCorpusOverview'
import { unitNoun, type CountUnit } from 'src/features/analytics/timeline'
import { INSPECT_OTHER, INSPECT_UNKNOWN, inspectedYears, toSearchCriteria, type Criteria, type Inspection, type ResultsMode } from './criteria'
import type { DocumentResults } from './useDocumentSearch'
import type { PassageResults } from './usePassageSearch'

/**
 * Charts of a text query's results (#620, docs/EXPLORATION.md): the counts of exactly the ids
 * the shown search ranked (`POST /api/analytics/results/distributions`, #619), for its mode,
 * criteria, vector and collection. Nothing is searched or ranked again for them, so the charts
 * and the Results describe the same population; a new search is a new population.
 */

/** What Visualizations show for a text query: its search, then the counts of its ranking. */
export interface RankedChartsState {
  /** The search is running: its ranking is not known yet. */
  searching: boolean
  searchError: string | null
  counts: RankedResultsDistributions | null
  slow: boolean
  error: string | null
  invalid: boolean
  vectorName: string | null
}

/** One search's ranking, as the Results hold it. */
export interface RankedPopulation {
  /** The search: a new search (or mode) is another population. */
  key: string
  mode: ResultsMode
  ids: string[]
  criteria: Criteria
  vector: string | null
  userCollectionId: string | null
  /** The retrieval limit cut the ranking: more results may match. */
  bounded: boolean
}

export function documentPopulation (results: DocumentResults): RankedPopulation | null {
  if (!results.ranked) return null
  return {
    key: `documents:${results.id}`,
    mode: 'documents',
    ids: results.ranked.map(r => r.id),
    criteria: results.query.criteria,
    vector: results.query.vector ?? null,
    userCollectionId: results.query.userCollectionId,
    bounded: results.bounded
  }
}

export function passagePopulation (results: PassageResults): RankedPopulation {
  return {
    key: `passages:${results.id}`,
    mode: 'passages',
    ids: [...results.rankedIds],
    criteria: results.query.criteria,
    vector: results.query.vector,
    userCollectionId: results.query.userCollectionId,
    bounded: results.bounded
  }
}

/**
 * The counts of the population last shown. `show` counts them unless the shown (or loading)
 * counts are already those of the same search; `force` (Retry) counts again. A newer request
 * aborts the previous one and its late answer is ignored; `clear` forgets the counts (the
 * search they describe is gone).
 */
export function useResultCharts () {
  const api = useApi().default
  const distributions = shallowRef<RankedResultsDistributions | null>(null)
  /** The population of `distributions` (or of the counts being loaded). */
  const population = shallowRef<RankedPopulation | null>(null)
  const loading = ref(false)
  const slow = ref(false)
  const error = ref<string | null>(null)
  /** Refused as invalid (400, 422): counting the same population again cannot help. */
  const invalid = ref(false)
  let controller: AbortController | null = null
  let slowTimer: ReturnType<typeof setTimeout> | null = null

  function stop () {
    controller?.abort()
    controller = null
    if (slowTimer) clearTimeout(slowTimer)
    slowTimer = null
  }

  async function show (requested: RankedPopulation, { force = false } = {}) {
    const current = population.value?.key === requested.key && !error.value && (loading.value || distributions.value !== null)
    if (current && !force) return
    stop()
    const mine = new AbortController()
    controller = mine
    population.value = requested
    distributions.value = null
    loading.value = true
    slow.value = false
    error.value = null
    invalid.value = false
    slowTimer = setTimeout(() => { slow.value = true }, SLOW_AFTER_MS)
    try {
      const result = await api.rankedResultsDistributionsApiAnalyticsResultsDistributionsPost({
        rankedResultsDistributionsRequest: {
          mode: requested.mode === 'documents' ? RankedResultsDistributionsRequestModeEnum.documents : RankedResultsDistributionsRequestModeEnum.passages,
          ids: requested.ids,
          criteria: toSearchCriteria(requested.criteria),
          userCollectionId: requested.userCollectionId,
          // Both Results searches rank a text query by hybrid search.
          ranking: { type: SearchType.hybrid, vector: requested.vector, bounded: requested.bounded },
          members: true
        }
      }, { signal: mine.signal })
      if (controller !== mine) return
      distributions.value = result
    } catch (e) {
      if (controller !== mine || isAbortError(e)) return
      console.error('Counting the search results failed', e)
      const message = await apiErrorMessage(e, 'The search results could not be counted.')
      if (controller !== mine) return
      error.value = message
      const status = errorStatus(e)
      invalid.value = status === 400 || status === 422
    } finally {
      if (controller === mine) {
        stop()
        loading.value = false
        slow.value = false
      }
    }
  }

  const retry = () => (population.value ? show(population.value, { force: true }) : Promise.resolve())

  function clear () {
    stop()
    population.value = null
    distributions.value = null
    loading.value = false
    slow.value = false
    error.value = null
    invalid.value = false
  }

  if (getCurrentScope()) onScopeDispose(stop)

  return { distributions, population, loading, slow, error, invalid, show, retry, clear }
}

/// ////////////
// Inspection //
/// ////////////

const listedValues = (distribution: CategoryDistribution) => new Set((distribution.values ?? []).map(v => v.value))

/**
 * The counted results of an inspected chart category, in ranking order: those the chart counts
 * in it, from the same answer. Null when the dimension is not available in this store.
 */
export function inspectedMembers (counts: RankedResultsDistributions, inspection: Inspection): ResultMember[] | null {
  const members = counts.members ?? []
  if (inspection.dimension === 'year') {
    if (!counts.publicationYear.available) return null
    if (inspection.value === INSPECT_UNKNOWN) return members.filter(m => m.year === null)
    const years = inspectedYears(inspection.value)
    return years ? members.filter(m => m.year !== null && m.year >= years.start && m.year <= years.end) : []
  }
  const distribution = inspection.dimension === 'library' ? counts.libraries : counts.languages
  if (!distribution.available) return null
  const valueOf = (m: ResultMember) => (inspection.dimension === 'library' ? m.library : m.language)
  if (inspection.value === INSPECT_UNKNOWN) return members.filter(m => valueOf(m) === null)
  if (inspection.value === INSPECT_OTHER) {
    const listed = listedValues(distribution)
    return members.filter(m => valueOf(m) !== null && !listed.has(valueOf(m)!))
  }
  return members.filter(m => valueOf(m) === inspection.value)
}

/** "published 1850–1859", "from Moravian Library (mzk)", "without a document language"… */
export function inspectionLabel (inspection: Inspection): string {
  const { dimension, value } = inspection
  if (dimension === 'year') {
    if (value === INSPECT_UNKNOWN) return 'without a valid publication year'
    const years = inspectedYears(value)
    return years && years.start !== years.end ? `published ${years.start}–${years.end}` : `published in ${value}`
  }
  if (dimension === 'library') {
    if (value === INSPECT_UNKNOWN) return 'without a source library'
    if (value === INSPECT_OTHER) return 'from libraries not listed in the chart'
    return `from ${libraryLabel(value)}`
  }
  if (value === INSPECT_UNKNOWN) return 'without a document language'
  if (value === INSPECT_OTHER) return 'in document languages not listed in the chart'
  return `in a document of ${languageLabel(value)}`
}

/** The counting unit of a mode's charts. */
export const modeUnit = (mode: ResultsMode): CountUnit => (mode === 'documents' ? 'documents' : 'passages')

/** "12 of the 300 ranked passages"; the noun follows the unit. */
export function inspectionCount (shown: number, counts: RankedResultsDistributions): string {
  const unit = modeUnit(counts.mode === 'documents' ? 'documents' : 'passages')
  const fmt = (n: number) => n.toLocaleString('en')
  return `${fmt(shown)} of the ${fmt(counts.totalCount)} counted ${unitNoun(unit, counts.totalCount)}`
}
