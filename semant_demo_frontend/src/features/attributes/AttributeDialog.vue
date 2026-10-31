<template>
  <FormDialog
    ref="dialogRef"
    :dirty="isDirty"
    :busy="saving"
    :pending="valuesBusy"
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
      <!-- While a save runs, nothing that goes into its request can change (#506). -->
      <q-form ref="formRef" class="q-gutter-y-md" @submit="submit">
        <q-input
          v-model="name"
          autofocus
          outlined
          label="Name"
          :disable="frozen"
          :rules="[(v: string) => !!v.trim() || 'Name is required', (v: string) => nameTaken(v, others()) ?? true]"
          :error="nameError ? true : undefined"
          :error-message="nameError ?? undefined"
          lazy-rules
          counter
          :maxlength="MAX_NAME"
        />
        <q-input
          v-model="description"
          outlined
          type="textarea"
          label="Description"
          hint="What the attribute records, so everyone assigns it the same way."
          :disable="frozen"
          :input-style="DESCRIPTION_STYLE"
          counter
          :maxlength="MAX_DESCRIPTION"
        />

        <div data-testid="attribute-cardinality">
          <q-toggle
            v-model="multiple"
            label="Allow multiple values per annotation"
            :disable="frozen || !!props.attribute"
          />
          <div v-if="props.attribute" class="text-caption text-grey-7 q-ml-sm">
            {{ multiple ? 'Annotations can have several values of this attribute.' : 'Annotations have at most one value of this attribute.' }}
            This cannot be changed after the attribute is created.
          </div>
          <div v-else-if="multiple" class="text-caption text-orange-10 q-ml-sm" role="status" data-testid="attribute-multiple-warning">
            <q-icon name="warning" size="16px" class="q-mr-xs" />This cannot be reversed later: an attribute that
            allows multiple values cannot go back to one value.
          </div>
        </div>

        <div data-testid="attribute-scope-section">
          <div class="text-subtitle1">Applies to</div>
          <q-option-group
            v-model="scope"
            :options="scopeOptions"
            :disable="frozen"
            data-testid="attribute-scope"
          />
          <q-select
            v-if="scope === 'selected'"
            v-model="tagIds"
            class="q-mt-sm"
            outlined
            multiple
            use-chips
            emit-value
            map-options
            use-input
            input-debounce="0"
            label="Tags"
            :disable="frozen"
            :options="tagOptions"
            :error="!!tagsError"
            :error-message="tagsError ?? undefined"
            :hint="tagIds.length ? undefined : 'No tags: no annotation can take values of this attribute.'"
            :rules="[
              () => sameTags || !deletedTagIds.length || 'Remove the deleted tags, or leave the tags unchanged'
            ]"
            @filter="filterTags"
          >
            <template #selected-item="item">
              <q-chip
                removable
                dense
                class="q-my-none q-ml-xs q-mr-none"
                :tabindex="item.tabindex"
                :disable="frozen"
                :color="isKnownTag(item.opt) ? undefined : 'grey-4'"
                :icon="isKnownTag(item.opt) ? undefined : 'label_off'"
                :data-testid="isKnownTag(item.opt) ? undefined : 'attribute-deleted-tag'"
                @remove="item.removeAtIndex(item.index)"
              >
                {{ isKnownTag(item.opt) ? item.opt.label : 'Deleted tag' }}
              </q-chip>
            </template>
          </q-select>
          <div v-else-if="tagsError" class="text-caption text-negative" role="alert">{{ tagsError }}</div>
        </div>

        <AttributeValuesEditor
          v-if="current"
          :attribute="current"
          :actions="props.valueActions!"
          :disabled="saving"
          @saved="keepSaved"
          @busy="(busy: boolean) => { valuesBusy = busy }"
        />

        <div v-else>
          <div class="text-subtitle1">Values</div>
          <div class="attribute-dialog__drafts">
            <div
              v-for="(draft, index) in drafts"
              :key="index"
              class="row items-start q-col-gutter-sm q-mb-sm"
              data-testid="attribute-dialog-value"
            >
              <div class="col">
                <q-input
                  v-model="drafts[index]"
                  outlined
                  dense
                  :label="`Value ${index + 1}`"
                  :disable="frozen"
                  :maxlength="MAX_NAME"
                  :rules="[() => draftTaken(index) ?? true]"
                  hide-bottom-space
                />
              </div>
              <div class="col-auto">
                <q-btn
                  flat
                  round
                  color="negative"
                  icon="delete"
                  :disable="frozen"
                  :aria-label="`Remove value ${index + 1}`"
                  @click="removeDraft(index)"
                />
              </div>
            </div>
          </div>
          <q-btn
            flat
            no-caps
            color="primary"
            icon="add"
            label="Add value"
            :disable="frozen || drafts.length + specialDrafts.length >= MAX_VALUES"
            @click="addDraft"
          />
          <div class="column q-mt-sm">
            <q-toggle
              v-for="kind in SPECIAL_KINDS"
              :key="kind"
              v-model="allowed[kind]"
              dense
              class="q-py-xs"
              :label="`Allow ${KIND_LABELS[kind]}`"
              :disable="frozen"
              :data-testid="`attribute-allow-${kind}`"
            />
          </div>
          <div class="text-caption text-grey-7">
            Unknown and Not applicable are explicit decisions, distinct from no value. Values can be added later.
          </div>
        </div>

        <q-banner
          v-if="error"
          ref="errorBanner"
          dense
          rounded
          class="bg-red-1 text-negative"
          role="alert"
          data-testid="attribute-dialog-error"
        >
          {{ error }}
        </q-banner>
      </q-form>
    </q-card-section>
  </FormDialog>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { QBanner, QForm, useDialogPluginComponent } from 'quasar'

import FormDialog from 'src/shared/ui/FormDialog.vue'
import { Cardinality, type Attribute, type PatchAttribute, type PostAttribute, type Tag } from 'src/generated/api'
import {
  DESCRIPTION_STYLE, KIND_LABELS, MAX_DESCRIPTION, MAX_NAME, MAX_VALUES, SPECIAL_KINDS, labelTaken, nameTaken,
  type SpecialKind, type ValueActions
} from './attributeForm'
import { AttributeWriteError } from './attributesStore'
import AttributeValuesEditor from './AttributeValuesEditor.vue'

type Save = (payload: PostAttribute | PatchAttribute) => Promise<Attribute>
type Tags = () => Tag[]
type Others = () => Attribute[]

const props = defineProps<{
  /** The attribute to edit; none: a new one. */
  attribute?: Attribute
  /** The collection's tags, for the tags it applies to; read when needed, so tags that arrive
   * while the dialog is open are offered. */
  tags: Tags
  /** Saves the attribute's own fields; the dialog stays open, showing the message, when it throws. */
  save: Save
  /** The value writes of an edited attribute, saved at once. */
  valueActions?: ValueActions
  /** The collection's other attributes, whose names this one cannot take; read when validated. */
  others?: Others
}>()

defineEmits([...useDialogPluginComponent.emits])
const { dialogRef, onDialogHide, onDialogOK } = useDialogPluginComponent()

const scopeOptions = [
  { label: 'All tags, including tags created later', value: 'all' },
  { label: 'Selected tags', value: 'selected' }
]

const formRef = ref<QForm | null>(null)
const name = ref(props.attribute?.name ?? '')
const description = ref(props.attribute?.description ?? '')
const multiple = ref(props.attribute?.cardinality === Cardinality.multi)
const initialTags = props.attribute?.tagIds ?? []
// All tags is explicit (allTags, #522): Selected tags with none chosen is no tag, never All tags.
// A new attribute starts at All tags for convenience; the dialog then sends allTags true.
const initialAll = props.attribute ? !!props.attribute.allTags : true
const scope = ref<'all' | 'selected'>(initialAll ? 'all' : 'selected')
const tagIds = ref<string[]>([...initialTags])
const drafts = ref<string[]>([''])
const allowed = reactive<Record<SpecialKind, boolean>>({ unknown: false, not_applicable: false })
const saving = ref(false)
const valuesBusy = ref(false)
const frozen = computed(() => saving.value || valuesBusy.value)
const error = ref<string | null>(null)
const errorBanner = ref<QBanner | null>(null)
// A name the server refused as taken (another person created it meanwhile), shown at the field.
const nameError = ref<string | null>(null)
watch(name, () => { nameError.value = null })
const others = () => props.others?.() ?? []

/** Why the draft value at `index` cannot be created: an earlier draft or an allowed special
 * value has its label. */
function draftTaken (index: number): string | null {
  const earlier = drafts.value.slice(0, index).map(label => ({ label }))
  const specials = specialDrafts.value.map(kind => ({ label: KIND_LABELS[kind], kind }))
  return labelTaken(drafts.value[index] ?? '', [...earlier, ...specials])
}
// A refusal of the tags (narrowing them while annotations hold values), shown at the field.
const tagsError = ref<string | null>(null)
watch([scope, tagIds], () => { tagsError.value = null })

// The edited attribute as last saved: value writes answer with it while the dialog is open.
const current = ref<Attribute | null>(props.attribute ?? null)
function keepSaved (attribute: Attribute) {
  if (!current.value || (attribute.revision ?? 0) >= (current.value.revision ?? 0)) current.value = attribute
}

const allTagOptions = computed(() => props.tags().map(tag => ({ label: tag.name, value: tag.id })))
// Applicable ids of tags deleted since (#508): shown as such, and they cannot be sent again.
const deletedTagIds = computed(() => {
  const known = new Set(props.tags().map(tag => tag.id))
  return tagIds.value.filter(id => !known.has(id))
})
// With emit-value and map-options, a selected id with no option comes as the bare id.
const isKnownTag = (opt: unknown): opt is { label: string } => typeof opt === 'object' && opt !== null
const tagFilter = ref('')
const tagOptions = computed(() => {
  const needle = tagFilter.value.toLowerCase()
  return needle ? allTagOptions.value.filter(o => o.label.toLowerCase().includes(needle)) : allTagOptions.value
})
function filterTags (value: string, update: (fn: () => void) => void) {
  update(() => { tagFilter.value = value })
}

const chosenTags = computed(() => scope.value === 'all' ? [] : tagIds.value)
const sameTags = computed(() =>
  chosenTags.value.length === initialTags.length && chosenTags.value.every(id => initialTags.includes(id)))
const sameScope = computed(() => (scope.value === 'all') === initialAll && sameTags.value)

const specialDrafts = computed(() => SPECIAL_KINDS.filter(kind => allowed[kind]))
const filledDrafts = computed(() => drafts.value.map(d => d.trim()).filter(d => d.length > 0))

const isDirty = computed(() =>
  name.value.trim() !== (props.attribute?.name ?? '') ||
  description.value.trim() !== (props.attribute?.description ?? '') ||
  !sameScope.value ||
  (!props.attribute && (multiple.value || filledDrafts.value.length > 0 || specialDrafts.value.length > 0))
)

async function addDraft () {
  drafts.value.push('')
  // The new row is at the end of a list that may scroll.
  await nextTick()
  const rows = document.querySelectorAll<HTMLInputElement>('[data-testid="attribute-dialog-value"] input')
  rows[rows.length - 1]?.focus()
}

function removeDraft (index: number) {
  if (drafts.value.length === 1) drafts.value[0] = ''
  else drafts.value.splice(index, 1)
}

function payload (): PostAttribute | PatchAttribute | null {
  if (!props.attribute) {
    return {
      name: name.value.trim(),
      description: description.value.trim(),
      cardinality: multiple.value ? Cardinality.multi : Cardinality.single,
      allTags: scope.value === 'all',
      tagIds: chosenTags.value,
      values: [
        ...filledDrafts.value.map(label => ({ label })),
        ...specialDrafts.value.map(kind => ({ label: KIND_LABELS[kind], kind }))
      ]
    }
  }
  const patch: PatchAttribute = {}
  if (name.value.trim() !== props.attribute.name) patch.name = name.value.trim()
  if (description.value.trim() !== (props.attribute.description ?? '')) patch.description = description.value.trim()
  if (!sameScope.value) {
    patch.allTags = scope.value === 'all'
    patch.tagIds = chosenTags.value
  }
  return Object.keys(patch).length ? patch : null
}

async function submit () {
  if (frozen.value) return
  error.value = null
  tagsError.value = null
  nameError.value = null
  const body = payload()
  if (!body) {
    onDialogOK(null)
    return
  }
  saving.value = true
  try {
    onDialogOK(await props.save(body))
  } catch (e) {
    const message = e instanceof Error ? e.message : 'The attribute could not be saved.'
    // Only a change of the tags is refused for annotations that hold values (409), or when
    // their number cannot be counted (503).
    const refusedTags = !!props.attribute && body.tagIds !== undefined && e instanceof AttributeWriteError &&
      (e.status === 409 || e.status === 503)
    if (refusedTags) tagsError.value = message
    else if (props.attribute && body.name !== undefined && message.startsWith('An attribute with this name')) {
      nameError.value = message
    } else {
      error.value = message
      // The form may be scrolled away from the message at its end.
      await nextTick()
      errorBanner.value?.$el?.scrollIntoView?.({ block: 'nearest' })
    }
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.attribute-dialog__drafts {
  max-height: 320px;
  overflow-y: auto;
}
</style>
