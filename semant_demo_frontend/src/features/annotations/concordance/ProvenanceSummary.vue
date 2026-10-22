<template>
  <div class="provenance text-caption" data-testid="annotation-provenance">
    <div v-if="unknown" data-testid="provenance-unknown">
      Origin unknown (created before provenance was recorded).
    </div>
    <div v-else data-testid="provenance-created">
      {{ provenance.origin === AnnotationOrigin.ai ? 'AI suggestion' : 'Created' }}
      {{ provenance.origin === AnnotationOrigin.ai ? 'run by' : 'by' }} {{ name(provenance.createdBy) }}<template
        v-if="provenance.createdAt">, {{ formatWhen(provenance.createdAt) }}</template>
      <span v-if="provenance.aiRunId" class="provenance__run">
        · run {{ provenance.aiRunId.slice(0, 8) }}
        <q-tooltip>AI suggestion run {{ provenance.aiRunId }}</q-tooltip>
      </span>
    </div>
    <div v-if="provenance.reviewedAt" data-testid="provenance-reviewed">
      {{ reviewVerb }} by {{ name(provenance.reviewedBy) }}, {{ formatWhen(provenance.reviewedAt) }}
    </div>
    <div v-if="editedAfterReview" data-testid="provenance-edited">
      Last changed by {{ name(provenance.lastEditedBy) }}, {{ formatWhen(provenance.lastEditedAt) }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { QTooltip } from 'quasar'
import { AnnotationOrigin, SpanType, type AnnotationProvenance, type CollectionPerson } from 'src/generated/api'
import { formatWhen, personName } from './provenance'

// Who created, last reviewed and last changed the focused annotation, and when (#460).
const props = defineProps<{
  provenance: AnnotationProvenance
  type: SpanType | null | undefined
  people: CollectionPerson[]
  /** The signed-in user, named "you". */
  me: string | null | undefined
}>()

const unknown = computed(() => (props.provenance.origin ?? AnnotationOrigin.unknown) === AnnotationOrigin.unknown &&
  !props.provenance.createdBy)

// The review is the last approve or reject; the current type tells which (unless changed since).
const reviewVerb = computed(() => ({
  [SpanType.pos]: 'Approved',
  [SpanType.neg]: 'Rejected'
} as Record<string, string>)[props.type ?? ''] ?? 'Reviewed')

// The last change is shown when it is not the review itself.
const editedAfterReview = computed(() => {
  const { lastEditedAt, reviewedAt } = props.provenance
  return !!lastEditedAt && lastEditedAt.getTime() !== reviewedAt?.getTime()
})

function name (id: string | null | undefined) {
  return personName(id, props.people, props.me)
}
</script>

<style scoped>
.provenance {
  display: flex;
  flex-direction: column;
  gap: 1px;
  color: rgba(0, 0, 0, 0.66);
  margin: 2px 0 4px;
}

.provenance__run {
  cursor: help;
}
</style>
