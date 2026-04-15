<template>
  <q-dialog ref="dialogRef" @hide="onDialogHide" persistent>
    <q-card class="q-pa-sm" style="width: 900px">
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
                @click="openColorPicker"
              >
                <q-tooltip>Choose tag color</q-tooltip>
              </q-btn>
            </div>

            <q-select
              class="col-6"
              v-model="tagPictogram"
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
                  clearable
                />
              </div>
              <div class="col-auto self-center">
                <q-btn
                  flat
                  round
                  color="negative"
                  icon="delete"
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
              @click="addExampleField"
            />
          </div>
        </q-form>
      </q-card-section>

      <q-card-actions align="right">
        <q-btn flat label="Cancel" color="primary" @click="handleCancel" />
        <q-btn
          unelevated
          color="primary"
          :label="props.dialogType === 'CREATE' ? 'Create' : 'Save'"
          @click="handleConfirm"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { QForm, useDialogPluginComponent, useQuasar } from 'quasar'
import useColorPicker from 'src/composables/useColorPicker'
import { PostTag, Tag } from 'src/models/tags'
import { computed, ref } from 'vue'

type DialogType = 'CREATE' | 'EDIT'

interface TagsDialogProps {
  dialogType: DialogType
  tag?: Tag
}

const $q = useQuasar()
const props = defineProps<TagsDialogProps>()
const { dialogRef, onDialogHide, onDialogCancel, onDialogOK } =
  useDialogPluginComponent()

const defaultTagPictogram = 'label'

defineEmits([...useDialogPluginComponent.emits])

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

const dialogTitle = props.dialogType === 'CREATE' ? 'Create Tag' : 'Edit Tag'
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

const isDirty = computed(() => {
  const originalExamples = (props.tag?.examples ?? [])
    .map((item: string) => item.trim())
    .filter((item: string) => item.length > 0)

  return (
    (tagName.value ?? '').trim() !== (props.tag?.name ?? '').trim() ||
    (tagShorthand.value ?? '').trim() !==
      (props.tag?.shorthand ?? '').trim() ||
    tagPictogram.value.trim() !==
      (props.tag?.pictogram ?? defaultTagPictogram).trim() ||
    (tagDefinition.value ?? '').trim() !==
      (props.tag?.definition ?? '').trim() ||
    currentColor.value !== (props.tag?.color ?? '#1976d2') ||
    JSON.stringify(normalizedExamples.value) !==
      JSON.stringify(originalExamples)
  )
})

const handleSubmit = async () => {
  const payload: PostTag = {
    name: tagName.value?.trim() ?? '',
    shorthand: tagShorthand.value?.trim() ?? '',
    color: currentColor.value,
    pictogram: tagPictogram.value.trim() || defaultTagPictogram,
    definition: tagDefinition.value?.trim() ?? '',
    examples: normalizedExamples.value
  }

  onDialogOK(payload)
}

const handleConfirmColor = () => {
  confirmColor()
  closeColor()
}

const handleCancel = () => {
  if (isDirty.value) {
    $q.dialog({
      title: 'Unsaved Changes',
      message:
        'You have unsaved changes. Are you sure you want to discard them?',
      ok: 'Yes',
      cancel: 'No',
      persistent: true
    }).onOk(() => {
      onDialogCancel()
    })
  } else {
    onDialogCancel()
  }
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
