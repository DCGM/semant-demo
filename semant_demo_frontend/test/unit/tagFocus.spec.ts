import { beforeEach, describe, expect, it } from 'vitest'
import { useTagNavigation } from 'src/features/annotations/useTagNavigation'

// The tag focused in the document view's tags panel (#479) and its interplay with tag visibility.
describe('tag focus', () => {
  const tagNav = useTagNavigation()

  beforeEach(() => {
    tagNav.setFocusedTagId(null)
    tagNav.showAllTags()
  })

  it('a second toggle on the focused tag ends the focus, another tag takes it over', () => {
    tagNav.toggleFocusedTag('a')
    expect(tagNav.focusedTagId.value).toBe('a')
    tagNav.toggleFocusedTag('b')
    expect(tagNav.focusedTagId.value).toBe('b')
    tagNav.toggleFocusedTag('b')
    expect(tagNav.focusedTagId.value).toBeNull()
  })

  it('focusing a hidden tag shows it', () => {
    tagNav.toggleTag('a')
    expect(tagNav.isTagVisible('a')).toBe(false)
    tagNav.setFocusedTagId('a')
    expect(tagNav.isTagVisible('a')).toBe(true)
  })

  it('hiding the focused tag ends the focus; hiding another tag keeps it', () => {
    tagNav.setFocusedTagId('a')
    tagNav.toggleTag('b')
    expect(tagNav.focusedTagId.value).toBe('a')
    tagNav.toggleTag('a')
    expect(tagNav.focusedTagId.value).toBeNull()

    tagNav.showAllTags()
    tagNav.setFocusedTagId('a')
    tagNav.hideAllTags(['a', 'b'])
    expect(tagNav.focusedTagId.value).toBeNull()
  })
})
