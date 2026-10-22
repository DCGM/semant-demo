<template>
  <!-- Asks before deleting; when annotations would go too, the user types DELETE (#479). -->
  <q-dialog ref="dialogRef" @hide="onDialogHide">
    <q-card style="width: 480px; max-width: 90vw">
      <q-card-section class="text-h6">{{ props.title }}</q-card-section>

      <q-card-section class="q-pt-none">
        <p>{{ props.message }} This cannot be undone.</p>

        <div v-if="state === 'counting'" class="row items-center q-gutter-sm text-grey-7">
          <q-spinner size="18px" />
          <span>Counting annotations…</span>
        </div>

        <q-banner v-else-if="mustType" rounded class="bg-red-1 text-negative q-mb-md">
          <template #avatar>
            <q-icon name="warning" color="negative" />
          </template>
          <template v-if="counts">
            This also deletes <strong>{{ annotationsText }}</strong>.
          </template>
          <template v-else>
            The annotations could not be counted; any annotations will be deleted too.
          </template>
        </q-banner>

        <q-input
          v-if="mustType"
          v-model="typed"
          outlined
          dense
          autofocus
          :label="`Type ${CONFIRM_WORD} to confirm`"
          @keyup.enter="confirm"
        />
      </q-card-section>

      <q-card-actions align="right">
        <q-btn flat label="Cancel" color="primary" @click="onDialogCancel" />
        <q-btn
          unelevated
          :label="props.okLabel ?? 'Delete'"
          color="negative"
          :disable="!canDelete"
          @click="confirm"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useDialogPluginComponent } from 'quasar'
import type { AnnotationCounter, AnnotationCounts } from 'src/features/annotations/annotationCounts'

const CONFIRM_WORD = 'DELETE'

const props = defineProps<{
  title: string
  /** What is deleted, as plain text (names are not HTML). */
  message: string
  okLabel?: string
  /** The annotations that would be deleted along. */
  count: AnnotationCounter
}>()

defineEmits([...useDialogPluginComponent.emits])
const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()

const state = ref<'counting' | 'counted' | 'failed'>('counting')
const counts = ref<AnnotationCounts | null>(null)
const typed = ref('')

const hasAnnotations = computed(() => !!counts.value && counts.value.approved + counts.value.suggestions > 0)
// Unknown counts are treated as "there may be annotations".
const mustType = computed(() => state.value === 'failed' || hasAnnotations.value)
const canDelete = computed(() =>
  state.value !== 'counting' && (!mustType.value || typed.value.trim() === CONFIRM_WORD)
)

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`
const annotationsText = computed(() => {
  if (!counts.value) return ''
  const { approved, suggestions } = counts.value
  const parts = []
  if (approved) parts.push(plural(approved, 'approved annotation', 'approved annotations'))
  if (suggestions) parts.push(plural(suggestions, 'unresolved AI suggestion', 'unresolved AI suggestions'))
  return parts.join(' and ')
})

const confirm = () => {
  if (canDelete.value) onDialogOK()
}

onMounted(async () => {
  try {
    counts.value = await props.count()
    state.value = 'counted'
  } catch (err) {
    console.error('Counting annotations failed', err)
    state.value = 'failed'
  }
})
</script>
