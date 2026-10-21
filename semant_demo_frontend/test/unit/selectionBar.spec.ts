import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { Quasar } from 'quasar'

import SelectionBar from 'src/features/annotations/concordance/SelectionBar.vue'
import type { ReviewReport } from 'src/features/annotations/concordance/annotationReviewStore'
import { ReviewAction } from 'src/generated/api'

// The workspace's selection and review bar (#459): explicit counts, hidden members, batch
// actions naming their target count, and per-item results with a retry of failed items.

const base = {
  selectedCount: 0,
  total: 120,
  hiddenSelected: 0,
  shownError: null,
  allSelected: false,
  resolving: false,
  tags: [],
  running: false,
  progress: 0,
  runningTarget: 0,
  report: null
}

const mountBar = (props: Partial<InstanceType<typeof SelectionBar>['$props']> = {}) =>
  mount(SelectionBar, { props: { ...base, ...props }, global: { plugins: [[Quasar, {}]] } })

const byTestId = (wrapper: ReturnType<typeof mountBar>, id: string) => wrapper.find(`[data-testid="${id}"]`)

describe('SelectionBar', () => {
  it('says when nothing is selected and offers all matches with their count', async () => {
    const wrapper = mountBar()
    expect(wrapper.text()).toContain('No annotations selected')
    expect(byTestId(wrapper, 'review-approve').exists()).toBe(false)
    await byTestId(wrapper, 'select-all-matches').trigger('click')
    expect(byTestId(wrapper, 'select-all-matches').text()).toBe('Select all 120 matches')
    expect(wrapper.emitted('select-all')).toHaveLength(1)
  })

  it('names the target count of batch actions and shows hidden members', async () => {
    const wrapper = mountBar({ selectedCount: 12, hiddenSelected: 3 })
    expect(byTestId(wrapper, 'review-approve').text()).toContain('Approve 12')
    expect(byTestId(wrapper, 'review-delete').text()).toContain('Delete 12…')
    expect(byTestId(wrapper, 'hidden-selected').text()).toContain('3 selected not shown by these filters')
    await byTestId(wrapper, 'review-reject').trigger('click')
    await byTestId(wrapper, 'deselect-hidden').trigger('click')
    expect(wrapper.emitted('review')).toEqual([[ReviewAction.reject]])
    expect(wrapper.emitted('deselect-hidden')).toHaveLength(1)
  })

  it('reports saved, failed, uncertain and missing items and retries only the failed ones', async () => {
    const report: ReviewReport = {
      action: ReviewAction.approve,
      tagId: null,
      target: 10,
      saved: ['a', 'b', 'c', 'd', 'e', 'f', 'g'],
      failed: [{ id: 'h', message: 'x', uncertain: false }, { id: 'i', message: 'y', uncertain: true }],
      missing: ['j'],
      unsynced: [],
      notSent: 0,
      error: null
    }
    const wrapper = mountBar({ selectedCount: 9, report })
    const text = byTestId(wrapper, 'review-report').text()
    expect(text).toContain('Approved 7 of 10.')
    expect(text).toContain('1 failed.')
    expect(text).toContain('1 uncertain')
    expect(text).toContain('1 no longer exist')
    expect(text).toContain('Saved changes are kept.')
    expect(byTestId(wrapper, 'review-retry').text()).toContain('Retry 2')
    await byTestId(wrapper, 'review-retry').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('offers to update search when only search references were not updated', async () => {
    const report: ReviewReport = {
      action: ReviewAction.delete,
      tagId: null,
      target: 2,
      saved: ['a', 'b'],
      failed: [],
      missing: [],
      unsynced: ['c1:t', 'c2:t'],
      notSent: 0,
      error: null
    }
    const wrapper = mountBar({ report })
    expect(byTestId(wrapper, 'review-report').text()).toContain('Search by tag does not reflect some changes yet (2 passages).')
    expect(byTestId(wrapper, 'review-retry').text()).toContain('Update search')
    await byTestId(wrapper, 'review-retry').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('disables actions while a review is running and shows its progress', () => {
    const wrapper = mountBar({ selectedCount: 400, running: true, progress: 200, runningTarget: 400 })
    expect(byTestId(wrapper, 'review-approve').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Saving 200 / 400')
  })
})
