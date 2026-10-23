import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { useApi } from 'src/shared/api'

/**
 * The Topicer configuration (AI model) for AI suggestions (#189), shared by the AI Tagging
 * panel and suggestions on a selection.
 *
 * The configurations are the ones Topicer has loaded (`GET /api/ai/topicer_configs`).
 * `load()` (panel mount, every run) reads them when they are older than `MAX_AGE_MS` or
 * were never read, `reload()` at once (after the backend refused the chosen model as
 * unknown). Until a read succeeds there is no picker (`failed` says why) and requests
 * name the remembered model, which the backend checks (an unknown one is refused, and the
 * list is then read again). The server default is always offered, also when Topicer does
 * not list it. The choice is remembered per browser; a remembered name that is not offered
 * falls back to the default.
 */

const STORAGE_KEY = 'semant.topicerConfig'
/** Age after which `load()` reads the list again (a Topicer redeploy may change it). */
export const MAX_AGE_MS = 5 * 60_000
/** The backend's `detail` for a request naming a model Topicer does not list. */
export const UNKNOWN_MODEL_DETAIL = 'Unknown AI model'
/** Shown instead of that refusal; the list read again then offers the default. */
export const UNKNOWN_MODEL_MESSAGE = 'The chosen AI model is no longer available; the default model is selected. ' +
  'Run the suggestions again.'

function readStored (): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function writeStored (name: string | null): void {
  try {
    if (name === null) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, name)
  } catch {
    // Storage unavailable (private mode, quota) — the choice just won't persist.
  }
}

export const useTopicerModelStore = defineStore('topicerModel', () => {
  const configs = ref<string[]>([])
  const defaultConfig = ref<string | null>(null)
  const loaded = ref(false)
  const failed = ref(false)
  let loadedAt = 0
  const stored = ref<string | null>(readStored())
  let loading: Promise<void> | null = null

  /** The models to offer: Topicer's configurations, and the server default first if it lists no such one. */
  const options = computed<string[]>(() =>
    defaultConfig.value === null || configs.value.includes(defaultConfig.value)
      ? configs.value
      : [defaultConfig.value, ...configs.value])

  /** The model in effect: the remembered choice when offered, otherwise the server default. */
  const selected = computed<string | null>({
    get: () => stored.value !== null && options.value.includes(stored.value) ? stored.value : defaultConfig.value,
    set: (name) => {
      stored.value = name === defaultConfig.value ? null : name
      writeStored(stored.value)
    }
  })

  async function read (): Promise<void> {
    try {
      const response = await useApi().default.getTopicerConfigsApiAiTopicerConfigsGet()
      configs.value = response.configs
      defaultConfig.value = response.defaultConfig
      loaded.value = true
      failed.value = false
      loadedAt = Date.now()
    } catch (e) {
      console.warn('Could not load the AI models for suggestions', e)
      // A list read earlier stays in use.
      failed.value = true
    } finally {
      loading = null
    }
  }

  /** Read the list unless it was read in the last `MAX_AGE_MS`; concurrent calls share one request. */
  async function load (): Promise<void> {
    if (loaded.value && Date.now() - loadedAt < MAX_AGE_MS) return
    await (loading ??= read())
  }

  /** Read the list again, e.g. after the backend refused the chosen model as unknown. */
  async function reload (): Promise<void> {
    await (loading ??= read())
  }

  /** The name to send with a suggestion request: `null` for the server default; before the list is read, the remembered one. */
  function chosenConfigName (): string | null {
    if (!loaded.value) return stored.value
    return selected.value !== null && selected.value !== defaultConfig.value ? selected.value : null
  }

  return { configs, defaultConfig, loaded, failed, options, selected, load, reload, chosenConfigName }
})
