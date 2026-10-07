import { describe, expect, it } from 'vitest'
import { ref } from 'vue'

import usePagination from 'src/composables/usePagination'

describe('usePagination', () => {
  it('returns no pages for an empty list', () => {
    const { pageCount, paginatedItems } = usePagination(ref<number[]>([]), ref(3))

    expect(pageCount.value).toBe(0)
    expect(paginatedItems.value).toEqual([])
  })

  it('splits items into pages including a partial last page', () => {
    const { pageCount, paginatedItems, setPage } = usePagination(ref([1, 2, 3, 4, 5, 6, 7]), ref(3))

    expect(pageCount.value).toBe(3)
    expect(paginatedItems.value).toEqual([1, 2, 3])

    setPage(3)
    expect(paginatedItems.value).toEqual([7])
  })

  it('has exactly one page when the item count equals the page size', () => {
    const { pageCount } = usePagination(ref([1, 2, 3]), ref(3))

    expect(pageCount.value).toBe(1)
  })

  it('follows changes of the source list and page size', () => {
    const items = ref([1, 2, 3, 4])
    const perPage = ref(2)
    const { pageCount, paginatedItems, setPage } = usePagination(items, perPage)

    setPage(2)
    expect(paginatedItems.value).toEqual([3, 4])

    items.value = [...items.value, 5]
    expect(pageCount.value).toBe(3)

    perPage.value = 4
    expect(pageCount.value).toBe(2)
    expect(paginatedItems.value).toEqual([5])
  })
})
