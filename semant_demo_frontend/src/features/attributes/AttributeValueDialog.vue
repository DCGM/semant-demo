<template>
  <FormDialog
    ref="dialogRef"
    :dirty="isDirty"
    :busy="saving"
    :ok-label="props.value ? 'Save' : 'Add'"
    @hide="onDialogHide"
    @confirm="formRef?.submit()"
  >
    <q-card-section>
      <div class="text-h4 text-grey-9 text-center">
        {{ props.value ? 'Edit Value' : 'Add Value' }}
      </div>
      <div class="text-subtitle1 text-grey-7 text-center">{{ props.attributeName }}</div>
    </q-card-section>

    <q-card-section>
      <q-form ref="formRef" class="q-gutter-y-md" @submit="submit">
        <q-input
          v-model="label"
          autofocus
          outlined
          label="Label"
          :rules="[(v: string) => !!v.trim() || 'Label is required']"
          lazy-rules
          counter
          :maxlength="MAX_NAME"
        />
        <q-select
          v-if="!props.value"
          v-model="kind"
          outlined
          emit-value
          map-options
          label="Kind"
          :options="kindChoices"
          hint="Unknown and Not applicable are explicit decisions, distinct from no value."
        />
        <div v-else class="text-body2">
          Kind: {{ KIND_LABELS[kind] }} <span class="text-grey-7">(cannot be changed)</span>
        </div>
        <q-input
          v-model="description"
          outlined
          type="textarea"
          autogrow
          label="Description"
          counter
          :maxlength="MAX_DESCRIPTION"
        />

        <div>
          <div class="text-subtitle1">Examples</div>
          <div
            v-for="(_, index) in examples"
            :key="index"
            class="row items-center q-col-gutter-sm q-mb-sm"
          >
            <div class="col">
              <q-input v-model="examples[index]" outlined dense :label="`Example ${index + 1}`" />
            </div>
            <div class="col-auto">
              <q-btn
                flat
                round
                color="negative"
                icon="delete"
                :aria-label="`Remove example ${index + 1}`"
                @click="removeExample(index)"
              />
            </div>
          </div>
          <q-btn
            flat
            no-caps
            color="primary"
            icon="add"
            label="Add example"
            :disable="examples.length >= MAX_EXAMPLES"
            @click="examples.push('')"
          />
        </div>

        <q-banner v-if="error" dense rounded class="bg-red-1 text-negative" role="alert" data-testid="value-dialog-error">
          {{ error }}
        </q-banner>
      </q-form>
    </q-card-section>
  </FormDialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { QForm, useDialogPluginComponent } from 'quasar'

import FormDialog from 'src/shared/ui/FormDialog.vue'
import { ValueKind, type AttributeValue, type PatchAttributeValue, type PostAttributeValue } from 'src/generated/api'
import { KIND_LABELS, MAX_DESCRIPTION, MAX_EXAMPLES, MAX_NAME, cleanList, kindOptions } from './attributeForm'

type Save = (payload: PostAttributeValue | PatchAttributeValue) => Promise<unknown>

const props = defineProps<{
  attributeName: string
  /** The value to edit; none: a new one. */
  value?: AttributeValue
  /** Special kinds the attribute already has (at most one of each). */
  takenKinds?: ValueKind[]
  /** Saves the form; the dialog stays open, showing the message, when it throws. */
  save: Save
}>()

defineEmits([...useDialogPluginComponent.emits])
const { dialogRef, onDialogHide, onDialogOK } = useDialogPluginComponent()

const formRef = ref<QForm | null>(null)
const label = ref(props.value?.label ?? '')
const kind = ref<ValueKind>(props.value?.kind ?? ValueKind.value)
const description = ref(props.value?.description ?? '')
const initialExamples = props.value?.examples ?? []
const examples = ref<string[]>(initialExamples.length ? [...initialExamples] : [''])
const saving = ref(false)
const error = ref<string | null>(null)

const kindChoices = computed(() => kindOptions.map(option => ({
  ...option,
  disable: option.value !== ValueKind.value && (props.takenKinds ?? []).includes(option.value)
})))

const sameExamples = computed(() =>
  JSON.stringify(cleanList(examples.value)) === JSON.stringify(cleanList(initialExamples)))

const isDirty = computed(() =>
  label.value.trim() !== (props.value?.label ?? '') ||
  description.value.trim() !== (props.value?.description ?? '') ||
  (!props.value && kind.value !== ValueKind.value) ||
  !sameExamples.value
)

function removeExample (index: number) {
  if (examples.value.length === 1) examples.value[0] = ''
  else examples.value.splice(index, 1)
}

function payload (): PostAttributeValue | PatchAttributeValue | null {
  if (!props.value) {
    return { label: label.value.trim(), kind: kind.value, description: description.value.trim(), examples: cleanList(examples.value) }
  }
  const patch: PatchAttributeValue = {}
  if (label.value.trim() !== props.value.label) patch.label = label.value.trim()
  if (description.value.trim() !== (props.value.description ?? '')) patch.description = description.value.trim()
  if (!sameExamples.value) patch.examples = cleanList(examples.value)
  return Object.keys(patch).length ? patch : null
}

async function submit () {
  if (saving.value) return
  error.value = null
  const body = payload()
  if (!body) {
    onDialogOK(null)
    return
  }
  saving.value = true
  try {
    onDialogOK(await props.save(body))
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'The value could not be saved.'
  } finally {
    saving.value = false
  }
}
</script>
