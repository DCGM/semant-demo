import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { MAX_AGE_MS, useTopicerModelStore } from 'src/features/annotations/topicerModelStore'
import { muteConsole } from './console'

// The model for AI suggestions (#189): Topicer's configurations, the server default
// unless the user picked another, remembered per browser.

const getConfigs = vi.fn()

vi.mock('src/shared/api', async () => ({
  ...(await vi.importActual<typeof import('src/shared/api')>('src/shared/api')),
  useApi: () => ({ default: { getTopicerConfigsApiAiTopicerConfigsGet: getConfigs } })
}))

const listed = (configs: string[], defaultConfig = configs[0]) => getConfigs.mockResolvedValue({ configs, defaultConfig })

/** The store of a fresh page load. */
function pageLoad () {
  setActivePinia(createPinia())
  return useTopicerModelStore()
}

describe('useTopicerModelStore', () => {
  beforeEach(() => {
    localStorage.clear()
    getConfigs.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('uses the server default until another model is picked, also before the list is read', async () => {
    listed(['llm', 'crossbert'])
    const model = pageLoad()
    expect([model.loaded, model.chosenConfigName()]).toEqual([false, null])
    await model.load()

    expect([model.options, model.selected, model.chosenConfigName()]).toEqual([['llm', 'crossbert'], 'llm', null])
    model.selected = 'crossbert'
    expect(model.chosenConfigName()).toBe('crossbert')
    model.selected = 'llm'
    expect(model.chosenConfigName()).toBeNull()
  })

  it('remembers the picked model across page loads', async () => {
    listed(['llm', 'crossbert'])
    const first = pageLoad()
    await first.load()
    first.selected = 'crossbert'

    const second = pageLoad()
    await second.load()

    expect(second.chosenConfigName()).toBe('crossbert')
  })

  it('falls back to the default when the remembered model is no longer offered', async () => {
    listed(['llm', 'crossbert'])
    const first = pageLoad()
    await first.load()
    first.selected = 'crossbert'

    listed(['llm'])
    const second = pageLoad()
    await second.load()

    expect([second.selected, second.chosenConfigName()]).toEqual(['llm', null])
  })

  it('offers the server default also when Topicer does not list it', async () => {
    listed(['crossbert'], 'llm')
    const model = pageLoad()
    await model.load()
    model.selected = 'crossbert'
    model.selected = 'llm'

    expect([model.options, model.chosenConfigName()]).toEqual([['llm', 'crossbert'], null])
  })

  it('reads the list once, again after a failed read, and on reload', async () => {
    const warn = muteConsole('warn')
    getConfigs.mockRejectedValueOnce(new Error('Topicer unavailable'))
    const model = pageLoad()
    await model.load()

    expect([model.loaded, model.failed, model.options, model.chosenConfigName()]).toEqual([false, true, [], null])
    expect(warn).toHaveBeenCalledWith('Could not load the AI models for suggestions', expect.any(Error))

    listed(['llm', 'crossbert'])
    await Promise.all([model.load(), model.load()])
    await model.load()
    expect(getConfigs).toHaveBeenCalledTimes(2)
    model.selected = 'crossbert'

    listed(['llm'])
    await model.reload()
    expect(getConfigs).toHaveBeenCalledTimes(3)
    expect(model.chosenConfigName()).toBeNull()
  })

  it('reads an outdated list again and keeps it when that read fails', async () => {
    vi.useFakeTimers()
    const warn = muteConsole('warn')
    listed(['llm', 'crossbert'])
    const model = pageLoad()
    await model.load()
    model.selected = 'crossbert'

    vi.advanceTimersByTime(MAX_AGE_MS - 1)
    await model.load()
    expect(getConfigs).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(2)
    getConfigs.mockRejectedValueOnce(new Error('Topicer unavailable'))
    await model.load()
    expect(getConfigs).toHaveBeenCalledTimes(2)
    expect(warn).toHaveBeenCalled()
    expect([model.loaded, model.failed, model.chosenConfigName()]).toEqual([true, true, 'crossbert'])

    listed(['llm', 'crossbert', 'qwen'])
    await model.load()
    expect([model.options, model.failed]).toEqual([['llm', 'crossbert', 'qwen'], false])
  })
})
