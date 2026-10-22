import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { useApi } from 'src/shared/api'

/**
 * The Topicer configuration (AI model) for AI suggestions (#189), shared by the AI Assist
 * panel and suggestions on a selection.
 *
 * The configurations are the ones Topicer has loaded (`GET /api/ai/topicer_configs`), read
 * once and again by `reload()` (after the backend refused a chosen model); a failed read
 * leaves the list unloaded (no picker, the server default is used) and is retried by the
 * next `load()`. The server default is always offered, also when Topicer does not list it.
 * The choice is remembered per browser; a remembered name that is not offered falls back
 * to the default.
 */

const STORAGE_KEY = 'semant.topicerConfig'

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
    } catch (e) {
      console.warn('Could not load the AI models for suggestions', e)
    } finally {
      loading = null
    }
  }

  /** Read the list unless it was read already; concurrent calls share one request. */
  async function load (): Promise<void> {
    if (loaded.value) return
    await (loading ??= read())
  }

  /** Read the list again, e.g. after the backend refused the chosen model as unknown. */
  async function reload (): Promise<void> {
    await (loading ??= read())
  }

  /** The name to send with a suggestion request: `null` for the server default (also before the list is read). */
  function chosenConfigName (): string | null {
    return selected.value !== null && selected.value !== defaultConfig.value ? selected.value : null
  }

  return { configs, defaultConfig, loaded, options, selected, load, reload, chosenConfigName }
})
