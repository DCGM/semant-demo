import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { Quasar } from 'quasar'

import ProvenanceSummary from 'src/features/annotations/concordance/ProvenanceSummary.vue'
import { AnnotationOrigin, SpanType, type AnnotationProvenance } from 'src/generated/api'

// Provenance of the focused annotation in the workspace sidebar (#460): who created, last
// reviewed and last changed it; actors by name, "you", or "a former member"; annotations
// saved before provenance was recorded say so instead of inventing an origin.

const people = [
  { id: 'jana', name: 'Jana Nováková', username: 'jana', role: 'owner' as const },
  { id: 'petr', name: null, username: 'petr', role: 'member' as const }
]
const at = (minute: number) => new Date(Date.UTC(2026, 9, 21, 12, minute))

const mountSummary = (provenance: AnnotationProvenance, type: SpanType = SpanType.pos) =>
  mount(ProvenanceSummary, { props: { provenance, type, people, me: 'petr' }, global: { plugins: [[Quasar, {}]] } })

const text = (wrapper: ReturnType<typeof mountSummary>, id: string) => wrapper.find(`[data-testid="${id}"]`)

describe('ProvenanceSummary', () => {
  it('says the origin is unknown for annotations saved before provenance was recorded', () => {
    const wrapper = mountSummary({ origin: AnnotationOrigin.unknown })
    expect(text(wrapper, 'provenance-unknown').text()).toContain('Origin unknown')
    expect(text(wrapper, 'provenance-created').exists()).toBe(false)
  })

  it('names the AI run, the creator, the review and a later change', () => {
    const wrapper = mountSummary({
      origin: AnnotationOrigin.ai,
      createdBy: 'jana',
      createdAt: at(0),
      aiRunId: '1a2b3c4d-0000-0000-0000-000000000000',
      reviewedBy: 'petr',
      reviewedAt: at(5),
      lastEditedBy: 'gone-user',
      lastEditedAt: at(9)
    })
    expect(text(wrapper, 'provenance-created').text()).toMatch(/AI suggestion run by Jana Nováková, .* run 1a2b3c4d/)
    expect(text(wrapper, 'provenance-reviewed').text()).toMatch(/^Approved by you, /)
    expect(text(wrapper, 'provenance-edited').text()).toMatch(/^Last changed by a former member, /)
  })

  it('does not repeat the review as the last change', () => {
    const wrapper = mountSummary({
      origin: AnnotationOrigin.manual,
      createdBy: 'petr',
      createdAt: at(0),
      reviewedBy: 'jana',
      reviewedAt: at(5),
      lastEditedBy: 'jana',
      lastEditedAt: at(5)
    }, SpanType.neg)
    expect(text(wrapper, 'provenance-created').text()).toMatch(/^Created by you, /)
    expect(text(wrapper, 'provenance-reviewed').text()).toMatch(/^Rejected by Jana Nováková, /)
    expect(text(wrapper, 'provenance-edited').exists()).toBe(false)
  })
})
