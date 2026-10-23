<template>
  <!-- Asks before deleting; when more would go too (e.g. annotations), the user types DELETE (#479). -->
  <q-dialog ref="dialogRef" @hide="onDialogHide">
    <q-card style="width: 480px; max-width: 90vw">
      <q-card-section class="text-h6">{{ props.title }}</q-card-section>

      <q-card-section class="q-pt-none">
        <p>{{ props.message }} This cannot be undone.</p>

        <div v-if="state === 'checking'" class="row items-center q-gutter-sm text-grey-7">
          <q-spinner size="18px" />
          <span>Checking what else would be deleted…</span>
        </div>

        <q-banner v-else-if="mustType" rounded class="bg-red-1 text-negative q-mb-md">
          <template #avatar>
            <q-icon name="warning" color="negative" />
          </template>
          <template v-if="state === 'checked'">
            This also deletes <strong>{{ alsoDeleted }}</strong>.
          </template>
          <template v-else>
            It could not be checked what else would be deleted; anything that belongs to it goes too.
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
          ref="deleteButton"
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
import { computed, nextTick, onMounted, ref } from 'vue'
import { QBtn, useDialogPluginComponent } from 'quasar'

const CONFIRM_WORD = 'DELETE'

/** Reads what else would be deleted along, as text; empty when nothing. */
type AlsoDeletes = () => Promise<string>

const props = defineProps<{
  title: string
  /** What is deleted, as plain text (names are not HTML). */
  message: string
  okLabel?: string
  /** e.g. "3 approved annotations" */
  alsoDeletes: AlsoDeletes
}>()

defineEmits([...useDialogPluginComponent.emits])
const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()

const state = ref<'checking' | 'checked' | 'failed'>('checking')
const alsoDeleted = ref('')
const typed = ref('')

// When the check fails, something may still be deleted along.
const mustType = computed(() => state.value === 'failed' || (state.value === 'checked' && !!alsoDeleted.value))
const canDelete = computed(() =>
  state.value !== 'checking' && (!mustType.value || typed.value.trim() === CONFIRM_WORD)
)

// Without anything else deleted it is a plain confirmation, so Enter deletes as before.
const deleteButton = ref<QBtn | null>(null)

const confirm = () => {
  if (canDelete.value) onDialogOK()
}

onMounted(async () => {
  try {
    alsoDeleted.value = await props.alsoDeletes()
    state.value = 'checked'
    if (!mustType.value) {
      await nextTick()
      ;(deleteButton.value?.$el as HTMLElement | undefined)?.focus()
    }
  } catch (err) {
    console.error('Checking what else would be deleted failed', err)
    state.value = 'failed'
  }
})
</script>
