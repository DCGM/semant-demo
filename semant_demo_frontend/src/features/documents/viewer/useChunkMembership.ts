import { computed, nextTick, ref } from 'vue'
import { useQuasar } from 'quasar'
import { IncompleteWriteError } from 'src/shared/writeOutcome'
import { useChunksRepository } from '../useChunksRepository'
import type { useChunkWindow } from './useChunkWindow'

type Settled = { status: 'fulfilled' } | { status: 'rejected', reason: unknown }

/**
 * A chunk is in the collection once its own link succeeded, even if linking its
 * document failed afterwards (IncompleteWriteError listing the chunk as succeeded).
 */
export function chunkLinked (outcome: Settled, chunkId: string): boolean {
  if (outcome.status === 'fulfilled') return true
  const err = outcome.reason
  return err instanceof IncompleteWriteError && (err.result.succeeded ?? []).includes(chunkId)
}

/**
 * Adds displayed chunks to the collection and removes them, one at a time from the
 * chunk gutter or in bulk for the selected chunks. Each chunk is a separate request;
 * chunks whose request failed keep their state and the failures are reported.
 */
export function useChunkMembership (
  collectionId: () => string, chunkWindow: ReturnType<typeof useChunkWindow>, relayout: () => void
) {
  const $q = useQuasar()
  const repository = useChunksRepository()
  const { displayChunks, findChunk } = chunkWindow

  // Which chunk is currently being added/removed
  const chunkLoadingId = ref<string | null>(null)
  const selectedChunkIds = ref<string[]>([])
  const bulkLoading = ref(false)

  const hasSelectedInCollection = computed(() =>
    selectedChunkIds.value.some(id => findChunk(id)?.inCollection)
  )
  const hasSelectedNotInCollection = computed(() =>
    selectedChunkIds.value.some(id => {
      const c = findChunk(id)
      return c !== undefined && !c.inCollection
    })
  )

  function toggleChunkSelection (chunkId: string) {
    const idx = selectedChunkIds.value.indexOf(chunkId)
    if (idx === -1) selectedChunkIds.value = [...selectedChunkIds.value, chunkId]
    else selectedChunkIds.value = selectedChunkIds.value.filter(id => id !== chunkId)
  }

  function clearChunkSelection () {
    selectedChunkIds.value = []
  }

  function selectAllVisible () {
    selectedChunkIds.value = displayChunks.value.map(c => c.id)
  }

  function selectAllNotInCollection () {
    selectedChunkIds.value = displayChunks.value.filter(c => !c.inCollection).map(c => c.id)
  }

  function notifyMembershipFailures (outcomes: Settled[], action: string) {
    const errors = outcomes.flatMap(o => (o.status === 'rejected' ? [o.reason] : []))
    if (!errors.length) return
    console.error(`${action} failed`, errors)
    const first = errors[0]
    $q.notify({
      type: 'negative',
      message: `${action}: ${errors.length} of ${outcomes.length} chunk(s) not fully updated.`,
      caption: first instanceof Error ? first.message : undefined,
      timeout: 6000
    })
  }

  async function addChunk (chunkId: string) {
    if (!findChunk(chunkId)) return
    chunkLoadingId.value = chunkId
    try {
      const [outcome] = await Promise.allSettled([repository.addChunkToCollection(chunkId, collectionId())])
      notifyMembershipFailures([outcome], 'Adding the chunk')
      if (!chunkLinked(outcome, chunkId)) return
      chunkWindow.setInCollection([chunkId], true)
    } finally {
      chunkLoadingId.value = null
    }
  }

  async function removeChunk (chunkId: string) {
    if (!findChunk(chunkId)) return
    chunkLoadingId.value = chunkId
    try {
      const [outcome] = await Promise.allSettled([repository.removeChunkFromCollection(chunkId, collectionId())])
      notifyMembershipFailures([outcome], 'Removing the chunk')
      if (outcome.status !== 'fulfilled') return
      // Keep chunk visible as a preview (inCollection = false), only hide on explicit hide action
      chunkWindow.setInCollection([chunkId], false)
      await nextTick()
      relayout()
      await chunkWindow.checkNeighbours()
    } finally {
      chunkLoadingId.value = null
    }
  }

  async function addSelected () {
    bulkLoading.value = true
    try {
      const candidates = selectedChunkIds.value.filter(id => !findChunk(id)?.inCollection)
      const outcomes = await Promise.allSettled(candidates.map(id => repository.addChunkToCollection(id, collectionId())))
      const toAdd = candidates.filter((id, i) => chunkLinked(outcomes[i], id))
      notifyMembershipFailures(outcomes, 'Adding chunks')
      chunkWindow.setInCollection(toAdd, true)
      selectedChunkIds.value = []
    } finally {
      bulkLoading.value = false
    }
  }

  async function removeSelected () {
    bulkLoading.value = true
    try {
      const candidates = selectedChunkIds.value.filter(id => findChunk(id)?.inCollection)
      const outcomes = await Promise.allSettled(candidates.map(id => repository.removeChunkFromCollection(id, collectionId())))
      const toRemove = candidates.filter((_, i) => outcomes[i].status === 'fulfilled')
      notifyMembershipFailures(outcomes, 'Removing chunks')
      chunkWindow.setInCollection(toRemove, false)
      selectedChunkIds.value = []
      await nextTick()
      relayout()
      await chunkWindow.checkNeighbours()
    } finally {
      bulkLoading.value = false
    }
  }

  return {
    chunkLoadingId,
    selectedChunkIds,
    bulkLoading,
    hasSelectedInCollection,
    hasSelectedNotInCollection,
    toggleChunkSelection,
    clearChunkSelection,
    selectAllVisible,
    selectAllNotInCollection,
    addChunk,
    removeChunk,
    addSelected,
    removeSelected
  }
}
