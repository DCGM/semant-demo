import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'

import type { PostTag, Tag } from 'src/generated/api'
import type { TagsDialogProps } from 'src/features/annotations/TagsDialogTypes'

// The four places that open Create/Edit Tag go through useTagEditing (#516). Its `onCreated`
// (the document reader tags the selected text with it) runs only when the dialog confirms that
// everything was saved; closing the dialog after the tag was created but an attribute change
// failed lists the tag and goes no further.

const fetchTagsByCollection = vi.fn()
const createTag = vi.fn()
const updateTag = vi.fn()
vi.mock('src/features/annotations/tagsStore', () => ({
  useTagsStore: () => ({ fetchTagsByCollection, createTag, updateTag })
}))

type Handler = (payload?: unknown) => unknown
let dialog: { props: TagsDialogProps, ok?: Handler, cancel?: Handler }
vi.mock('src/features/annotations/useTagsDialog', () => ({
  default: () => ({
    openTagsDialog: (props: TagsDialogProps) => {
      dialog = { props }
      const chain = {
        onOk: (fn: Handler) => { dialog.ok = fn; return chain },
        onCancel: (fn: Handler) => { dialog.cancel = fn; return chain }
      }
      return chain
    }
  })
}))

const { useTagEditing } = await import('src/features/annotations/useTagEditing')

const created = { id: 't9', name: 'Speaker', shorthand: 'S' } as Tag
const payload = { name: 'Speaker', shorthand: 'S' } as PostTag

beforeEach(() => {
  fetchTagsByCollection.mockReset().mockResolvedValue(undefined)
  createTag.mockReset().mockResolvedValue(created)
  updateTag.mockReset().mockResolvedValue(created)
})

describe('useTagEditing', () => {
  it('goes on with a created tag only when the dialog confirms', async () => {
    const onCreated = vi.fn()
    useTagEditing(() => 'c1').createTag(onCreated)
    await dialog.props.save(payload, null)
    expect(createTag).toHaveBeenCalledWith('c1', payload)
    await dialog.ok!(created)
    await flushPromises()
    expect(fetchTagsByCollection).toHaveBeenCalledWith('c1')
    expect(onCreated).toHaveBeenCalledWith(created)
  })

  it('lists a tag created before the dialog was closed, without going on with it', async () => {
    const onCreated = vi.fn()
    useTagEditing(() => 'c1').createTag(onCreated)
    await dialog.props.save(payload, null)
    await dialog.cancel!()
    await flushPromises()
    expect(fetchTagsByCollection).toHaveBeenCalledWith('c1')
    expect(onCreated).not.toHaveBeenCalled()
  })

  it('reads nothing again when the dialog is closed without saving', async () => {
    useTagEditing(() => 'c1').createTag(vi.fn())
    createTag.mockRejectedValue(new Error('A tag with this name already exists'))
    await expect(dialog.props.save(payload, null)).rejects.toThrow()
    await dialog.cancel!()
    await flushPromises()
    expect(fetchTagsByCollection).not.toHaveBeenCalled()
  })
})
