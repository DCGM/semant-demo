import { onActivated, onBeforeUnmount, onDeactivated, onMounted } from 'vue'

/**
 * Runs `start` while the component is shown and `stop` when it is hidden or unmounted: on a
 * page kept alive (router/keptPages.ts) also when it is left and shown again, so its window
 * listeners (keys, clicks) do not act on the page shown instead of it.
 */
export function whileShown (start: () => void, stop: () => void) {
  let running = false
  const on = () => {
    if (running) return
    running = true
    start()
  }
  const off = () => {
    if (!running) return
    running = false
    stop()
  }
  onMounted(on)
  onActivated(on)
  onDeactivated(off)
  onBeforeUnmount(off)
}
