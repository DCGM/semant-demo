import { computed, type Ref, ref } from 'vue'

const usePagination = <T>(allItems: Ref<T[]>, itemsPerPage: Ref<number> = ref(10)) => {
  const currentPage = ref(1)

  const pageCount = computed(() => {
    return Math.ceil(allItems.value.length / itemsPerPage.value)
  })

  const paginatedItems = computed(() => {
    const start = (currentPage.value - 1) * itemsPerPage.value
    const end = start + itemsPerPage.value
    return allItems.value.slice(start, end)
  })

  const setPage = (newPage: number) => {
    currentPage.value = newPage
  }

  return {
    currentPage,
    pageCount,
    paginatedItems,
    setPage
  }
}

export default usePagination
