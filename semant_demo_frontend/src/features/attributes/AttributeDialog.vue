<template>
  <FormDialog
    ref="dialogRef"
    :dirty="isDirty"
    :busy="saving"
    :ok-label="props.attribute ? 'Save' : 'Create'"
    @hide="onDialogHide"
    @confirm="formRef?.submit()"
  >
    <q-card-section>
      <div class="text-h4 text-grey-9 text-center">
        {{ props.attribute ? 'Edit Attribute' : 'Create Attribute' }}
      </div>
    </q-card-section>

    <q-card-section>
      <q-form ref="formRef" class="q-gutter-y-md" @submit="submit">
        <q-input
          v-model="name"
          autofocus
          outlined
          label="Name"
          :rules="[(v: string) => !!v.trim() || 'Name is required']"
          lazy-rules
          counter
          :maxlength="MAX_NAME"
        />
        <q-input
          v-model="description"
          outlined
          type="textarea"
          autogrow
          label="Description"
          hint="What the attribute records, so everyone assigns it the same way."
          counter
          :maxlength="MAX_DESCRIPTION"
        />

        <div>
          <div class="text-subtitle1">Values per annotation</div>
          <q-option-group
            v-if="!props.attribute"
            v-model="cardinality"
            :options="cardinalityOptions"
            inline
          />
          <div v-else class="text-body2" data-testid="attribute-cardinality">
            {{ cardinalityOptions.find(o => o.value === cardinality)?.label }}
            <span class="text-grey-7">(cannot be changed after creation)</span>
          </div>
        </div>

        <q-select
          v-model="tagIds"
          outlined
          multiple
          use-chips
          emit-value
          map-options
          use-input
          input-debounce="0"
          label="Applies to tags"
          hint="Leave empty to apply to annotations of every tag."
          :options="tagOptions"
          @filter="filterTags"
        />

        <div v-if="!props.attribute">
          <div class="text-subtitle1">Values</div>
          <div
            v-for="(value, index) in values"
            :key="index"
            class="row items-start q-col-gutter-sm q-mb-sm"
            data-testid="attribute-dialog-value"
          >
            <div class="col-12 col-sm">
              <q-input
                v-model="value.label"
                outlined
                dense
                :label="`Value ${index + 1}`"
                :maxlength="MAX_NAME"
              />
            </div>
            <div class="col col-sm-auto" style="min-width: 170px">
              <q-select
                v-model="value.kind"
                outlined
                dense
                emit-value
                map-options
                :options="kindOptions"
                aria-label="Kind"
              />
            </div>
            <div class="col-auto">
              <q-btn
                flat
                round
                color="negative"
                icon="delete"
                :aria-label="`Remove value ${index + 1}`"
                @click="removeValue(index)"
              />
            </div>
          </div>
          <q-btn
            flat
            no-caps
            color="primary"
            icon="add"
            label="Add value"
            :disable="values.length >= MAX_VALUES"
            @click="values.push({ label: '', kind: ValueKind.value })"
          />
          <div class="text-caption text-grey-7">
            Unknown and Not applicable are explicit decisions, distinct from no value. More values can be added later.
          </div>
        </div>

        <q-banner v-if="error" dense rounded class="bg-red-1 text-negative" role="alert" data-testid="attribute-dialog-error">
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
import { Cardinality, ValueKind, type Attribute, type PatchAttribute, type PostAttribute, type Tag } from 'src/generated/api'
import { KIND_LABELS, MAX_DESCRIPTION, MAX_NAME, MAX_VALUES, kindOptions, repeatedKinds } from './attributeForm'

type Save = (payload: PostAttribute | PatchAttribute) => Promise<unknown>

const props = defineProps<{
  /** The attribute to edit; none: a new one. */
  attribute?: Attribute
  /** The collection's tags, for the tags it applies to. */
  tags: Tag[]
  /** Saves the form; the dialog stays open, showing the message, when it throws. */
  save: Save
}>()

defineEmits([...useDialogPluginComponent.emits])
const { dialogRef, onDialogHide, onDialogOK } = useDialogPluginComponent()

const cardinalityOptions = [
  { label: 'One value', value: Cardinality.single },
  { label: 'Several values', value: Cardinality.multi }
]

const formRef = ref<QForm | null>(null)
const name = ref(props.attribute?.name ?? '')
const description = ref(props.attribute?.description ?? '')
const cardinality = ref<Cardinality>(props.attribute?.cardinality ?? Cardinality.single)
const initialTags = props.attribute?.tagIds ?? []
const tagIds = ref<string[]>([...initialTags])
const values = ref<{ label: string, kind: ValueKind }[]>([{ label: '', kind: ValueKind.value }])
const saving = ref(false)
const error = ref<string | null>(null)

const allTagOptions = computed(() => props.tags.map(tag => ({ label: tag.name, value: tag.id })))
const tagFilter = ref('')
const tagOptions = computed(() => {
  const needle = tagFilter.value.toLowerCase()
  return needle ? allTagOptions.value.filter(o => o.label.toLowerCase().includes(needle)) : allTagOptions.value
})
function filterTags (value: string, update: (fn: () => void) => void) {
  update(() => { tagFilter.value = value })
}

const sameTags = computed(() =>
  tagIds.value.length === initialTags.length && tagIds.value.every(id => initialTags.includes(id)))

const isDirty = computed(() =>
  name.value.trim() !== (props.attribute?.name ?? '') ||
  description.value.trim() !== (props.attribute?.description ?? '') ||
  (!props.attribute && cardinality.value !== Cardinality.single) ||
  !sameTags.value ||
  (!props.attribute && values.value.some(v => v.label.trim()))
)

function removeValue (index: number) {
  if (values.value.length === 1) values.value[0] = { label: '', kind: ValueKind.value }
  else values.value.splice(index, 1)
}

function payload (): PostAttribute | PatchAttribute | null {
  if (!props.attribute) {
    return {
      name: name.value.trim(),
      description: description.value.trim(),
      cardinality: cardinality.value,
      tagIds: tagIds.value,
      values: values.value
        .filter(v => v.label.trim())
        .map(v => ({ label: v.label.trim(), kind: v.kind }))
    }
  }
  const patch: PatchAttribute = {}
  if (name.value.trim() !== props.attribute.name) patch.name = name.value.trim()
  if (description.value.trim() !== (props.attribute.description ?? '')) patch.description = description.value.trim()
  if (!sameTags.value) patch.tagIds = tagIds.value
  return Object.keys(patch).length ? patch : null
}

async function submit () {
  if (saving.value) return
  error.value = null
  const repeated = props.attribute ? [] : repeatedKinds(values.value.filter(v => v.label.trim()).map(v => v.kind))
  if (repeated.length) {
    error.value = `An attribute has at most one ${KIND_LABELS[repeated[0]!]} value.`
    return
  }
  const body = payload()
  if (!body) {
    onDialogOK(null)
    return
  }
  saving.value = true
  try {
    onDialogOK(await props.save(body))
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'The attribute could not be saved.'
  } finally {
    saving.value = false
  }
}
</script>
