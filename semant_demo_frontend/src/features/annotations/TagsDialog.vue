<template>
  <FormDialog
    ref="dialogRef"
    :dirty="isDirty"
    :ok-label="savedTag ? 'Save' : 'Create'"
    :busy="saving"
    @hide="onHide"
    @confirm="handleConfirm"
  >
    <q-card-section>
      <div class="text-h4 text-grey-9 text-center">
        {{ dialogTitle }}
      </div>
    </q-card-section>

    <q-card-section>
      <q-form ref="formRef" class="q-gutter-y-lg" @submit="handleSubmit">
        <q-input
          v-model="tagName"
          autofocus
          :disable="saving"
          :rules="tagNameRules"
          lazy-rules
          outlined
          label="Tag Name"
          clearable
          counter
          maxlength="80"
        />

        <q-input
          v-model="tagShorthand"
          :disable="saving"
          :rules="tagShorthandRules"
          lazy-rules
          outlined
          label="Tag Shorthand"
          clearable
          counter
          maxlength="10"
        />

        <div class="q-mt-md row items-center">
          <div class="col-6">
            <span
              class="q-mr-sm text-grey-10"
              style="
                padding: 0 12px;
                border-radius: 8px;
                font-size: 15px;
                letter-spacing: 0.5px;
              "
            >
              Tag Color:
            </span>

            <q-btn
              round
              size="md"
              :style="{ backgroundColor: currentColor }"
              outlined
              unelevated
              class="q-mr-sm"
              :disable="saving"
              @click="openColorPicker"
            >
              <q-tooltip>Choose tag color</q-tooltip>
            </q-btn>
          </div>

          <q-select
            class="col-6"
            v-model="tagPictogram"
            :disable="saving"
            outlined
            label="Tag Pictogram"
            :options="tagPictogramOptions"
            emit-value
            map-options
          >
            <template #selected>
              <div class="row items-center no-wrap" style="min-height: 32px">
                <q-icon :name="tagPictogram" size="30px" />
              </div>
            </template>

            <template #option="scope">
              <q-item v-bind="scope.itemProps" class="q-py-sm">
                <q-item-section avatar>
                  <q-icon :name="scope.opt.value" size="25px" />
                </q-item-section>
              </q-item>
            </template>
          </q-select>

          <q-dialog v-model="showColorPicker">
            <q-card>
              <q-card-section>
                <q-color v-model="tempColor" format="hex" />
              </q-card-section>
              <q-card-section align="right">
                <q-btn
                  flat
                  label="Cancel"
                  color="primary"
                  @click="closeColor"
                />
                <q-btn
                  unelevated
                  label="Confirm"
                  color="primary"
                  @click="handleConfirmColor"
                />
              </q-card-section>
            </q-card>
          </q-dialog>
        </div>

        <q-input
          v-model="tagDefinition"
          :disable="saving"
          outlined
          label="Tag Definition"
          type="textarea"
          counter
          maxlength="1000"
          hint="Provide a clear and concise definition for this tag."
        />

        <div>
          <div class="row items-center q-mb-sm">
            <div class="text-subtitle1">Examples</div>
          </div>

          <div
            v-for="(example, index) in tagExamples"
            :key="`example-${index}`"
            class="row items-center q-col-gutter-sm q-mb-sm"
          >
            <div class="col">
              <q-input
                v-model="tagExamples[index]"
                outlined
                :label="`Example ${index + 1}`"
                :disable="saving"
                clearable
              />
            </div>
            <div class="col-auto self-center">
              <q-btn
                flat
                round
                color="negative"
                icon="delete"
                :disable="saving"
                @click="removeExampleField(index)"
              >
                <q-tooltip>Delete example</q-tooltip>
              </q-btn>
            </div>
          </div>

          <q-btn
            flat
            color="primary"
            icon="add"
            label="Add Example"
            no-caps
            :disable="saving"
            @click="addExampleField"
          />
        </div>

        <TagApplicableAttributes
          v-model:wanted="wanted"
          :attributes="attributes"
          :tag-id="savedTag?.id ?? null"
          :errors="attributeErrors"
          :loading="attributesLoading"
          :error="attributesError"
          :disable="saving"
          @retry="loadAttributes"
        />

        <div v-if="formError" class="text-negative" role="alert" data-testid="tag-dialog-error">
          {{ formError }}
        </div>
      </q-form>
    </q-card-section>

  </FormDialog>
</template>

<script setup lang="ts">
import FormDialog from 'src/shared/ui/FormDialog.vue'
import { QForm, useDialogPluginComponent } from 'quasar'
import { storeToRefs } from 'pinia'
import useColorPicker from 'src/shared/useColorPicker'
import { plural } from 'src/shared/plural'
import { apiErrorMessage } from 'src/shared/api'
import { PostTag, Tag } from 'src/generated/api'
import { computed, onMounted, ref } from 'vue'
import TagApplicableAttributes from 'src/features/attributes/TagApplicableAttributes.vue'
import { useAttributesStore } from 'src/features/attributes/attributesStore'
import { tagApplicabilityChanges } from 'src/features/attributes/attributeForm'
import { TagsDialogProps } from './TagsDialogTypes'

// The dialog saves on its own and closes only when everything is saved (#516): first the tag,
// then one change per attribute whose applicability to it was switched. They are separate
// writes: a tag saved before an attribute change fails stays saved (Create becomes Edit), the
// failed changes are shown at their attributes and Save tries them again. Only a save of
// everything confirms the dialog (`ok`, on which the caller may go on, e.g. tag the selected
// text); closing it before that is a dismissal even when the tag was saved, and the caller learns
// of that tag from its `save`. After a failed attribute change, closing reloads the attributes, as
// they may have been changed by someone else.
const props = defineProps<TagsDialogProps>()
defineEmits([...useDialogPluginComponent.emits])
const { dialogRef, onDialogHide, onDialogOK } =
  useDialogPluginComponent()

const defaultTagPictogram = 'label'

const {
  currentColor,
  showColorPicker,
  tempColor,
  openColorPicker,
  confirmColor,
  closeColor
} = useColorPicker(props.tag?.color ?? '#1976d2')

const tagName = ref<string | null>(props.tag?.name ?? null)
const tagShorthand = ref<string | null>(props.tag?.shorthand ?? null)
const tagPictogram = ref<string>(
  props.tag?.pictogram?.trim() || defaultTagPictogram
)
const tagDefinition = ref<string | null>(props.tag?.definition ?? null)
const tagExamples = ref<string[]>(
  props.tag?.examples?.length
    ? [...props.tag.examples]
    : ['']
)

// The tag as saved: the one edited, or the one this dialog created.
const savedTag = ref<Tag | null>(props.tag ?? null)
let confirmed = false
let attributeChangeFailed = false
const saving = ref(false)
const formError = ref<string | null>(null)
const attributeErrors = ref<Record<string, string>>({})
const wanted = ref<Record<string, boolean>>({})

const attributesStore = useAttributesStore()
const { attributes, loading: attributesLoading, error: attributesError } = storeToRefs(attributesStore)
const loadAttributes = () => attributesStore.load(props.collectionId)
onMounted(loadAttributes)

const pendingChanges = computed(() =>
  tagApplicabilityChanges(attributes.value, savedTag.value?.id ?? null, wanted.value))

const dialogTitle = computed(() => savedTag.value ? 'Edit Tag' : 'Create Tag')
const formRef = ref<QForm | null>(null)
const tagPictogramOptions = [
  { label: 'Label', value: 'label' },
  { label: 'Tag', value: 'sell' },
  { label: 'Bookmark', value: 'bookmark' },
  { label: 'Push Pin', value: 'push_pin' },
  { label: 'Location', value: 'place' },
  { label: 'Circle', value: 'lens' },
  { label: 'Square', value: 'square' },
  { label: 'Hexagon', value: 'hexagon' },
  { label: 'Star', value: 'star' },
  { label: 'Heart', value: 'favorite' },
  { label: 'Flag', value: 'flag' },
  { label: 'Folder', value: 'folder' },
  { label: 'Question', value: 'help' },
  { label: 'Info', value: 'info' }
]

const normalizedExamples = computed<string[]>(() => {
  return tagExamples.value
    .map((item: string) => item.trim())
    .filter((item: string) => item.length > 0)
})

const addExampleField = () => {
  tagExamples.value.push('')
}

const removeExampleField = (index: number) => {
  if (tagExamples.value.length === 1) {
    tagExamples.value[0] = ''
    return
  }

  tagExamples.value.splice(index, 1)
}

const tagDirty = computed(() => {
  const saved = savedTag.value
  const originalExamples = (saved?.examples ?? [])
    .map((item: string) => item.trim())
    .filter((item: string) => item.length > 0)

  return (
    (tagName.value ?? '').trim() !== (saved?.name ?? '').trim() ||
    (tagShorthand.value ?? '').trim() !==
      (saved?.shorthand ?? '').trim() ||
    tagPictogram.value.trim() !==
      (saved?.pictogram?.trim() || defaultTagPictogram) ||
    (tagDefinition.value ?? '').trim() !==
      (saved?.definition ?? '').trim() ||
    currentColor.value !== (saved?.color ?? '#1976d2') ||
    JSON.stringify(normalizedExamples.value) !==
      JSON.stringify(originalExamples)
  )
})

const isDirty = computed(() => tagDirty.value || pendingChanges.value.length > 0)

const handleSubmit = async () => {
  if (saving.value) return
  const payload: PostTag = {
    name: tagName.value?.trim() ?? '',
    shorthand: tagShorthand.value?.trim() ?? '',
    color: currentColor.value,
    pictogram: tagPictogram.value.trim() || defaultTagPictogram,
    definition: tagDefinition.value?.trim() ?? '',
    examples: normalizedExamples.value
  }

  saving.value = true
  formError.value = null
  attributeErrors.value = {}
  try {
    // Whether this save wrote the tag: only then is the failure of an attribute change worth
    // saying the tag is saved (a new tag exists although the dialog stays open).
    const tagSaved = !savedTag.value || tagDirty.value
    if (tagSaved) {
      try {
        savedTag.value = await props.save(payload, savedTag.value)
      } catch (e) {
        formError.value = await apiErrorMessage(e, 'The tag could not be saved.')
        return
      }
    }
    const tag = savedTag.value
    if (!tag) return
    const tagId = tag.id
    const changes = tagApplicabilityChanges(attributes.value, tagId, wanted.value)
    const results = await Promise.allSettled(changes.map(({ attribute, add }) =>
      attributesStore.updateAttribute(props.collectionId, attribute.id,
        add ? { addTagIds: [tagId] } : { removeTagIds: [tagId] })))
    const errors: Record<string, string> = {}
    results.forEach((result, index) => {
      if (result.status === 'rejected') {
        const reason: unknown = result.reason
        errors[changes[index]!.attribute.id] =
          reason instanceof Error && reason.message ? reason.message : 'The change could not be saved.'
      }
    })
    const failed = Object.keys(errors).length
    if (!failed) {
      confirmed = true
      onDialogOK(tag)
      return
    }
    attributeChangeFailed = true
    attributeErrors.value = errors
    const what = plural(failed, 'attribute change')
    const were = failed === 1 ? 'was' : 'were'
    formError.value = tagSaved
      ? `The tag is saved, but ${what} ${were} not; Save tries again.`
      : `${what} ${were} not saved; Save tries again.`
  } finally {
    saving.value = false
  }
}

const onHide = () => {
  if (!confirmed && attributeChangeFailed) void loadAttributes()
  onDialogHide()
}

const handleConfirmColor = () => {
  confirmColor()
  closeColor()
}

const handleConfirm = () => {
  formRef.value?.submit()
}

const tagNameRules = [
  (val: string | null) => !!val?.trim() || 'Tag name is required'
]
const tagShorthandRules = [
  (val: string | null) => !!val?.trim() || 'Tag shorthand is required'
]
</script>
