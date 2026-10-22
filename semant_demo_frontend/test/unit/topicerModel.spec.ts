import { beforeEach, describe, expect, it, vi } from 'vitest'

import { resetTopicerModel, useTopicerModel } from 'src/features/annotations/topicerModel'
import { muteConsole } from './console'

// The model for AI suggestions (#189): Topicer's configurations, the server default
// unless the user picked another, remembered per browser.

const getConfigs = vi.fn()

vi.mock('src/shared/api', async () => ({
  ...(await vi.importActual<typeof import('src/shared/api')>('src/shared/api')),
  useApi: () => ({ default: { getTopicerConfigsApiAiTopicerConfigsGet: getConfigs } })
}))

const listed = (configs: string[], defaultConfig = configs[0]) => getConfigs.mockResolvedValue({ configs, defaultConfig })

describe('useTopicerModel', () => {
  beforeEach(() => {
    localStorage.clear()
    getConfigs.mockReset()
    resetTopicerModel()
  })

  it('uses the server default until another model is picked', async () => {
    listed(['llm', 'crossbert'])
    const model = useTopicerModel()
    await model.load()

    expect([model.configs.value, model.selected.value, model.chosenConfigName()]).toEqual([['llm', 'crossbert'], 'llm', null])
    model.selected.value = 'crossbert'
    expect(model.chosenConfigName()).toBe('crossbert')
    model.selected.value = 'llm'
    expect(model.chosenConfigName()).toBeNull()
  })

  it('remembers the picked model across page loads', async () => {
    listed(['llm', 'crossbert'])
    const model = useTopicerModel()
    await model.load()
    model.selected.value = 'crossbert'

    resetTopicerModel()
    await model.load()

    expect(model.chosenConfigName()).toBe('crossbert')
  })

  it('falls back to the default when the remembered model is no longer offered', async () => {
    listed(['llm', 'crossbert'])
    const model = useTopicerModel()
    await model.load()
    model.selected.value = 'crossbert'

    listed(['llm'])
    resetTopicerModel()
    await model.load()

    expect([model.selected.value, model.chosenConfigName()]).toEqual(['llm', null])
  })

  it('reads the list once, and again after a failed read', async () => {
    const warn = muteConsole('warn')
    getConfigs.mockRejectedValueOnce(new Error('Topicer unavailable'))
    const model = useTopicerModel()
    await model.load()

    expect([model.configs.value, model.chosenConfigName()]).toEqual([[], null])
    expect(warn).toHaveBeenCalledWith('Could not load the AI models for suggestions', expect.any(Error))

    listed(['llm'])
    await Promise.all([model.load(), model.load()])
    await model.load()
    expect(getConfigs).toHaveBeenCalledTimes(2)
    expect(model.configs.value).toEqual(['llm'])
  })
})
