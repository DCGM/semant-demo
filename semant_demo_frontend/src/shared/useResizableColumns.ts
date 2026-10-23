import { computed, onBeforeUnmount, ref, type Ref } from 'vue'
import type { QTableColumn } from 'quasar'

const MIN_WIDTH = 60
const STORAGE_PREFIX = 'semant.columnWidths.'

function readWidths (key: string): Record<string, number> {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_PREFIX + key) ?? '{}')
    if (!parsed || typeof parsed !== 'object') return {}
    return Object.fromEntries(Object.entries(parsed).filter(
      (entry): entry is [string, number] => typeof entry[1] === 'number' && entry[1] >= MIN_WIDTH
    ))
  } catch {
    return {}
  }
}

function writeWidths (key: string, widths: Record<string, number>): void {
  try {
    localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(widths))
  } catch {
    // Storage unavailable (private mode, quota) — the widths just won't persist.
  }
}

/**
 * Column widths a user sets by dragging the right edge of a QTable header cell (#479),
 * remembered per table (`storageKey`) in this browser. A column keeps its natural width
 * until it is dragged; a double-click on the edge gives it back. `columns` gets the widths
 * as cell styles; the header slot calls `startResize` and `resetWidth` from its handle.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- QTableColumn's own row constraint
export function useResizableColumns<Row extends Record<string, any>> (storageKey: string, baseColumns: QTableColumn<Row>[]) {
  const widths: Ref<Record<string, number>> = ref(readWidths(storageKey))
  let drag: { name: string, startX: number, startWidth: number, handle: HTMLElement, pointerId: number } | null = null

  const columns = computed<QTableColumn<Row>[]>(() => baseColumns.map((col) => {
    const width = widths.value[col.name]
    if (!width) return col
    // Fixed width; text longer than that is cut with an ellipsis.
    const sized = `width: ${width}px; min-width: ${width}px; max-width: ${width}px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;`
    return {
      ...col,
      headerStyle: `${col.headerStyle ?? ''}; ${sized}`,
      style: `${typeof col.style === 'string' ? col.style : ''}; ${sized}`
    }
  }))

  function onPointerMove (e: PointerEvent) {
    if (!drag || e.pointerId !== drag.pointerId) return
    const width = Math.max(MIN_WIDTH, Math.round(drag.startWidth + e.clientX - drag.startX))
    widths.value = { ...widths.value, [drag.name]: width }
  }

  function stopResize () {
    if (!drag) return
    drag.handle.removeEventListener('pointermove', onPointerMove)
    drag.handle.removeEventListener('pointerup', stopResize)
    drag.handle.removeEventListener('pointercancel', stopResize)
    drag = null
    writeWidths(storageKey, widths.value)
  }

  /** Starts dragging the edge of column `name`; the handle sits inside its header cell. */
  function startResize (e: PointerEvent, name: string) {
    if (e.button !== 0) return
    const handle = e.currentTarget as HTMLElement
    const th = handle.closest('th')
    if (!th) return
    stopResize()
    drag = { name, startX: e.clientX, startWidth: th.getBoundingClientRect().width, handle, pointerId: e.pointerId }
    handle.setPointerCapture(e.pointerId)
    handle.addEventListener('pointermove', onPointerMove)
    handle.addEventListener('pointerup', stopResize)
    handle.addEventListener('pointercancel', stopResize)
  }

  /** Gives column `name` its natural width back. */
  function resetWidth (name: string) {
    const rest = { ...widths.value }
    delete rest[name]
    widths.value = rest
    writeWidths(storageKey, rest)
  }

  onBeforeUnmount(stopResize)

  return { columns, startResize, resetWidth }
}
