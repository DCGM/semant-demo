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
      <div class="text-subtitle1 text-grey-7 text-center attribute-value-dialog__attribute">{{ props.attributeName }}</div>
    </q-card-section>

    <q-card-section>
      <!-- While saving, nothing that goes into the request can change. -->
      <q-form ref="formRef" class="q-gutter-y-md" @submit="submit">
        <q-input
          v-model="label"
          autofocus
          outlined
          label="Label"
          :disable="saving"
          :rules="[(v: string) => !!v.trim() || 'Label is required', (v: string) => labelTaken(v, props.others ?? []) ?? true]"
          :error="labelError ? true : undefined"
          :error-message="labelError ?? undefined"
          lazy-rules
          counter
          :maxlength="MAX_NAME"
        />
        <q-input
          v-model="description"
          outlined
          type="textarea"
          label="Description"
          :disable="saving"
          :input-style="DESCRIPTION_STYLE"
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
              <q-input v-model="examples[index]" outlined dense :disable="saving" :label="`Example ${index + 1}`" />
            </div>
            <div class="col-auto">
              <q-btn
                flat
                round
                color="negative"
                icon="delete"
                :disable="saving"
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
            :disable="saving || examples.length >= MAX_EXAMPLES"
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
import { computed, ref, watch } from 'vue'
import { QForm, useDialogPluginComponent } from 'quasar'

import FormDialog from 'src/shared/ui/FormDialog.vue'
import type { AttributeValue, PatchAttributeValue, PostAttributeValue } from 'src/generated/api'
import { DESCRIPTION_STYLE, MAX_DESCRIPTION, MAX_EXAMPLES, MAX_NAME, TAKEN_LABEL, cleanList, isTaken, labelTaken } from './attributeForm'

type Save = (payload: PostAttributeValue | PatchAttributeValue) => Promise<unknown>

// An ordinary value of an attribute; Unknown and Not applicable are fixed and are offered or
// withdrawn in the attribute dialog instead (#506).
const props = defineProps<{
  attributeName: string
  /** The value to edit; none: a new one. */
  value?: AttributeValue
  /** Saves the form; the dialog stays open, showing the message, when it throws. */
  save: Save
  /** The attribute's other values, whose labels this one cannot take. */
  others?: AttributeValue[]
}>()

defineEmits([...useDialogPluginComponent.emits])
const { dialogRef, onDialogHide, onDialogOK } = useDialogPluginComponent()

const formRef = ref<QForm | null>(null)
const label = ref(props.value?.label ?? '')
const description = ref(props.value?.description ?? '')
const initialExamples = props.value?.examples ?? []
const examples = ref<string[]>(initialExamples.length ? [...initialExamples] : [''])
const saving = ref(false)
const error = ref<string | null>(null)
// A label the server refused as taken (added by another person meanwhile), shown at the field.
const labelError = ref<string | null>(null)
watch(label, () => { labelError.value = null })

const sameExamples = computed(() =>
  JSON.stringify(cleanList(examples.value)) === JSON.stringify(cleanList(initialExamples)))

const isDirty = computed(() =>
  label.value.trim() !== (props.value?.label ?? '') ||
  description.value.trim() !== (props.value?.description ?? '') ||
  !sameExamples.value
)

function removeExample (index: number) {
  if (examples.value.length === 1) examples.value[0] = ''
  else examples.value.splice(index, 1)
}

function payload (): PostAttributeValue | PatchAttributeValue | null {
  if (!props.value) {
    return { label: label.value.trim(), description: description.value.trim(), examples: cleanList(examples.value) }
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
  labelError.value = null
  const body = payload()
  if (!body) {
    onDialogOK(null)
    return
  }
  saving.value = true
  try {
    onDialogOK(await props.save(body))
  } catch (e) {
    const message = e instanceof Error ? e.message : 'The value could not be saved.'
    if (isTaken(e, TAKEN_LABEL)) labelError.value = message
    else error.value = message
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.attribute-value-dialog__attribute {
  overflow-wrap: anywhere;
}
</style>
