import { computed, ref } from 'vue'
import { useApi } from 'src/shared/api'

/**
 * The Topicer configuration (AI model) for AI suggestions (#189), shared by the AI Assist
 * panel and suggestions on a selection.
 *
 * The configurations are the ones Topicer has loaded (`GET /api/ai/topicer_configs`),
 * read once per page load; a failed read leaves the list empty (no picker, the server
 * default is used) and is retried on the next `load()`. The choice is remembered
 * per browser; a remembered name that is no longer offered falls back to the default.
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

const configs = ref<string[]>([])
const defaultConfig = ref<string | null>(null)
const stored = ref<string | null>(readStored())
let loading: Promise<void> | null = null

/** The configuration in effect: the remembered choice when offered, otherwise the server default. */
const selected = computed<string | null>({
  get: () => stored.value !== null && configs.value.includes(stored.value) ? stored.value : defaultConfig.value,
  set: (name) => {
    stored.value = name === defaultConfig.value ? null : name
    writeStored(stored.value)
  }
})

async function load (): Promise<void> {
  if (configs.value.length) return
  loading ??= (async () => {
    try {
      const response = await useApi().default.getTopicerConfigsApiAiTopicerConfigsGet()
      configs.value = response.configs
      defaultConfig.value = response.defaultConfig
    } catch (e) {
      console.warn('Could not load the AI models for suggestions', e)
    } finally {
      loading = null
    }
  })()
  await loading
}

/** The name to send with a suggestion request: `null` for the server default. */
function chosenConfigName (): string | null {
  return selected.value !== null && selected.value !== defaultConfig.value ? selected.value : null
}

/** Forget the loaded list (tests). The remembered choice is re-read from storage. */
export function resetTopicerModel (): void {
  configs.value = []
  defaultConfig.value = null
  stored.value = readStored()
  loading = null
}

export function useTopicerModel () {
  return { configs, defaultConfig, selected, load, chosenConfigName }
}
