import { computed, nextTick, ref } from 'vue'
import type { CollectionChunk } from 'src/generated/api'
import { useChunksRepository } from '../useChunksRepository'

/**
 * The chunks the reader shows: the collection's chunks of a document plus preview chunks
 * loaded around them, and hidden chunks that are kept only for offset math across gaps.
 * `relayout` is called after the displayed chunks changed and were rendered.
 */
export function useChunkWindow (
  collectionId: () => string, documentId: () => string, relayout: () => void
) {
  const repository = useChunksRepository()

  // Local display chunks — a superset of collection chunks plus any expanded previews
  const displayChunks = ref<CollectionChunk[]>([])
  // Hidden chunks needed for cross-gap span projection (e.g. a span bridging a removed chunk)
  const hiddenPreviewChunks = ref<CollectionChunk[]>([])

  // Whether neighbour chunks exist in the DB beyond what we're showing
  const hasPrev = ref(false)
  const hasNext = ref(false)
  const loadingPrev = ref(false)
  const loadingNext = ref(false)
  const loadingAllPrev = ref(false)
  const loadingAllNext = ref(false)
  const gapLoadingKey = ref<string | null>(null)
  const loadingAllChunks = ref(false)

  const displayedPreviewCount = computed(() => displayChunks.value.filter(c => !c.inCollection).length)
  const allChunksShown = computed(() =>
    !hasPrev.value && !hasNext.value && hiddenPreviewChunks.value.length === 0 && displayChunks.value.length > 0
  )

  const findChunk = (chunkId: string) => displayChunks.value.find(c => c.id === chunkId)

  const relayoutAfterRender = async () => {
    await nextTick()
    relayout()
  }

  /** Replaces the displayed chunks (the collection's chunks were loaded). */
  function show (chunks: CollectionChunk[]) {
    displayChunks.value = [...chunks]
  }

  // ── Check if neighbours exist ──
  async function checkNeighbours () {
    if (!displayChunks.value.length) { hasPrev.value = false; hasNext.value = false; return }
    const minOrder = Math.min(...displayChunks.value.map(c => c.order))
    const maxOrder = Math.max(...displayChunks.value.map(c => c.order))
    const [prev, next] = await Promise.all([
      repository.getNeighbourChunk(collectionId(), documentId(), 'prev', minOrder),
      repository.getNeighbourChunk(collectionId(), documentId(), 'next', maxOrder)
    ])
    hasPrev.value = prev !== null
    hasNext.value = next !== null
  }

  // ── Pre-load gap chunks for cross-gap span rendering ──
  // Fetches chunks that sit in document gaps between displayed chunks and stores
  // them in hiddenPreviewChunks so useAnnotations can do correct offset math.
  async function preloadGapChunks () {
    const display = displayChunks.value
    const fetches: Promise<void>[] = []
    for (let i = 0; i < display.length - 1; i++) {
      if (display[i + 1].order === display[i].order + 1) continue
      const afterOrder = display[i].order
      const beforeOrder = display[i + 1].order
      fetches.push(
        repository.getChunksInRange(collectionId(), documentId(), afterOrder, beforeOrder)
          .then(gaps => {
            for (const g of gaps) {
              if (!hiddenPreviewChunks.value.find(h => h.id === g.id) &&
                  !displayChunks.value.find(d => d.id === g.id)) {
                hiddenPreviewChunks.value.push(g)
              }
            }
          })
          .catch(e => console.warn('preloadGapChunks failed:', e))
      )
    }
    await Promise.all(fetches)
  }

  // ── Load all neighbouring chunks in one direction ──
  async function loadAllNeighbours (direction: 'prev' | 'next') {
    if (direction === 'prev') loadingAllPrev.value = true
    else loadingAllNext.value = true
    try {
      const boundary = direction === 'prev'
        ? Math.min(...displayChunks.value.map(c => c.order))
        : Math.max(...displayChunks.value.map(c => c.order))
      const chunks = await repository.getChunksInRange(
        collectionId(),
        documentId(),
        direction === 'next' ? boundary : null,
        direction === 'prev' ? boundary : null
      )
      if (chunks.length) {
        if (direction === 'prev') {
          displayChunks.value = [...chunks, ...displayChunks.value]
        } else {
          displayChunks.value = [...displayChunks.value, ...chunks]
        }
      }
      await relayoutAfterRender()
      if (direction === 'prev') hasPrev.value = false
      else hasNext.value = false
    } finally {
      if (direction === 'prev') loadingAllPrev.value = false
      else loadingAllNext.value = false
    }
  }

  // ── Load a neighbouring chunk into the display list ──
  async function loadNeighbour (direction: 'prev' | 'next') {
    if (direction === 'prev') loadingPrev.value = true
    else loadingNext.value = true
    try {
      const boundaryOrder = direction === 'prev'
        ? Math.min(...displayChunks.value.map(c => c.order))
        : Math.max(...displayChunks.value.map(c => c.order))
      const chunk = await repository.getNeighbourChunk(collectionId(), documentId(), direction, boundaryOrder)
      if (!chunk) {
        if (direction === 'prev') hasPrev.value = false
        else hasNext.value = false
        return
      }
      if (direction === 'prev') {
        displayChunks.value = [chunk, ...displayChunks.value]
      } else {
        displayChunks.value = [...displayChunks.value, chunk]
      }
      await relayoutAfterRender()
      // Only re-check the direction we loaded — the other side couldn't have changed
      const newBoundary = direction === 'prev'
        ? Math.min(...displayChunks.value.map(c => c.order))
        : Math.max(...displayChunks.value.map(c => c.order))
      const further = await repository.getNeighbourChunk(collectionId(), documentId(), direction, newBoundary)
      if (direction === 'prev') hasPrev.value = further !== null
      else hasNext.value = further !== null
    } finally {
      if (direction === 'prev') loadingPrev.value = false
      else loadingNext.value = false
    }
  }

  // ── Load a single chunk just after afterOrder (into the gap) ──
  async function loadGap (afterOrder: number) {
    gapLoadingKey.value = `${afterOrder}:next`
    try {
      const chunk = await repository.getNeighbourChunk(collectionId(), documentId(), 'next', afterOrder)
      if (!chunk) return
      const idx = displayChunks.value.findIndex(c => c.order === afterOrder)
      if (idx === -1) return
      displayChunks.value = [
        ...displayChunks.value.slice(0, idx + 1),
        chunk,
        ...displayChunks.value.slice(idx + 1)
      ]
      await relayoutAfterRender()
    } finally {
      gapLoadingKey.value = null
    }
  }

  // ── Load a single chunk just before beforeOrder (into the gap) ──
  async function loadGapPrev (beforeOrder: number) {
    gapLoadingKey.value = `${beforeOrder}:prev`
    try {
      const chunk = await repository.getNeighbourChunk(collectionId(), documentId(), 'prev', beforeOrder)
      if (!chunk) return
      const idx = displayChunks.value.findIndex(c => c.order === beforeOrder)
      if (idx === -1) return
      displayChunks.value = [
        ...displayChunks.value.slice(0, idx),
        chunk,
        ...displayChunks.value.slice(idx)
      ]
      await relayoutAfterRender()
    } finally {
      gapLoadingKey.value = null
    }
  }

  // ── Load all missing chunks between afterOrder and beforeOrder ──
  async function loadGapAll (afterOrder: number, beforeOrder: number) {
    gapLoadingKey.value = `${afterOrder}:all`
    try {
      const newChunks = await repository.getChunksInRange(collectionId(), documentId(), afterOrder, beforeOrder)
      if (newChunks.length) {
        const idx = displayChunks.value.findIndex(c => c.order === afterOrder)
        if (idx !== -1) {
          displayChunks.value = [
            ...displayChunks.value.slice(0, idx + 1),
            ...newChunks,
            ...displayChunks.value.slice(idx + 1)
          ]
        }
      }
      await relayoutAfterRender()
    } finally {
      gapLoadingKey.value = null
    }
  }

  async function loadAllChunks () {
    loadingAllChunks.value = true
    try {
      const all = await repository.getChunksInRange(collectionId(), documentId())
      const merged = [...all]
      merged.sort((a, b) => a.order - b.order)
      displayChunks.value = merged.filter((c, i, arr) => arr.findIndex(x => x.id === c.id) === i)
      hiddenPreviewChunks.value = []
      hasPrev.value = false
      hasNext.value = false
      await relayoutAfterRender()
    } finally {
      loadingAllChunks.value = false
    }
  }

  // ── Load exactly the chunks between the window and a target order (#249) ──
  // Used to jump to a document-summary citation whose chunk isn't displayed yet: unlike
  // loadAllNeighbours/loadAllChunks, this loads only up to targetOrder (bounded by how far it
  // is from the current window), not the rest of the document in that direction. A target
  // order that falls *inside* the displayed range (a partial-membership gap) delegates to the
  // existing loadGapAll between the two chunks straddling it.
  async function loadUntil (targetOrder: number): Promise<void> {
    if (!displayChunks.value.length) return
    const orders = displayChunks.value.map(c => c.order).sort((a, b) => a - b)
    const minOrder = orders[0]
    const maxOrder = orders[orders.length - 1]
    if (targetOrder > maxOrder) {
      loadingNext.value = true
      try {
        const chunks = await repository.getChunksInRange(collectionId(), documentId(), maxOrder, targetOrder + 1)
        if (chunks.length) displayChunks.value = [...displayChunks.value, ...chunks]
      } finally {
        loadingNext.value = false
      }
      await relayoutAfterRender()
      await checkNeighbours()
    } else if (targetOrder < minOrder) {
      loadingPrev.value = true
      try {
        const chunks = await repository.getChunksInRange(collectionId(), documentId(), targetOrder - 1, minOrder)
        if (chunks.length) displayChunks.value = [...chunks, ...displayChunks.value]
      } finally {
        loadingPrev.value = false
      }
      await relayoutAfterRender()
      await checkNeighbours()
    } else if (!displayChunks.value.some(c => c.order === targetOrder)) {
      // Inside the displayed range but missing: a gap from non-contiguous collection
      // membership. orders is sorted and targetOrder is strictly between its ends, so there
      // is always a next-greater entry here.
      const afterIdx = orders.findIndex(o => o > targetOrder) - 1
      await loadGapAll(orders[afterIdx], orders[afterIdx + 1])
    }
  }

  /** Stops showing a chunk; a preview chunk is kept hidden for offset math. */
  function hideChunk (chunkId: string) {
    const chunk = findChunk(chunkId)
    if (chunk && !chunk.inCollection) hiddenPreviewChunks.value.push(chunk)
    displayChunks.value = displayChunks.value.filter(c => c.id !== chunkId)
    void nextTick().then(() => { relayout(); void checkNeighbours() })
  }

  /** Shows only the collection's chunks. */
  function hideAllPreviews () {
    const previews = displayChunks.value.filter(c => !c.inCollection)
    hiddenPreviewChunks.value = [...hiddenPreviewChunks.value, ...previews.filter(
      p => !hiddenPreviewChunks.value.find(h => h.id === p.id)
    )]
    displayChunks.value = displayChunks.value.filter(c => c.inCollection)
    void nextTick().then(() => { relayout(); void checkNeighbours() })
  }

  /** Marks displayed chunks as in or out of the collection. */
  function setInCollection (chunkIds: string[], inCollection: boolean) {
    displayChunks.value = displayChunks.value.map(c =>
      chunkIds.includes(c.id) ? { ...c, inCollection } : c
    )
  }

  return {
    displayChunks,
    hiddenPreviewChunks,
    hasPrev,
    hasNext,
    loadingPrev,
    loadingNext,
    loadingAllPrev,
    loadingAllNext,
    gapLoadingKey,
    loadingAllChunks,
    displayedPreviewCount,
    allChunksShown,
    findChunk,
    show,
    checkNeighbours,
    preloadGapChunks,
    loadAllNeighbours,
    loadNeighbour,
    loadGap,
    loadGapPrev,
    loadGapAll,
    loadAllChunks,
    loadUntil,
    hideChunk,
    hideAllPreviews,
    setInCollection
  }
}
