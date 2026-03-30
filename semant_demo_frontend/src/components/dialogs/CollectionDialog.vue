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
            v-model="title"
            autofocus
            :rules="titleRules"
            lazy-rules
            outlined
            label="Collection Name"
            clearable
            counter
            maxlength="50"
          />
          <q-input
            v-model="description"
            outlined
            label="Collection Description"
            type="textarea"
            counter
            maxlength="300"
          />
        </q-form>
        <div class="q-mt-md flex items-center">
          <span
            class="q-mr-sm text-grey-10"
            style="
              padding: 0px 12px;
              border-radius: 8px;
              font-size: 15px;
              letter-spacing: 0.5px;
            "
          >
            Collection Color:
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
            <q-tooltip> Choose collection color </q-tooltip>
          </q-btn>
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
import { CollectionDialogProps } from './CollectionDialogTypes'
import useColorPicker from 'src/composables/useColorPicker'
import { computed, ref } from 'vue'

const $q = useQuasar()
const props = defineProps<CollectionDialogProps>()
const { dialogRef, onDialogHide, onDialogCancel, onDialogOK } =
  useDialogPluginComponent()

const {
  currentColor,
  showColorPicker,
  tempColor,
  openColorPicker,
  confirmColor,
  closeColor
} = useColorPicker(props.collection?.color ?? '#1976d2')

defineEmits([...useDialogPluginComponent.emits])

const title = ref<string | null>(props.collection?.name ?? null)
const description = ref<string | null>(props.collection?.description ?? null)

const dialogTitle =
  props.dialogType === 'CREATE' ? 'Create Collection' : 'Edit Collection'
const formRef = ref<QForm | null>(null)

const isDirty = computed(() => {
  return (
    (title.value ?? '').trim() !== (props.collection?.name ?? '').trim() ||
    (description.value ?? '').trim() !==
      (props.collection?.description ?? '').trim()
  )
})

const handleSubmit = async () => {
  onDialogOK({
    name: title.value?.trim() ?? '',
    description: description.value?.trim() ?? '',
    color: currentColor.value
  })
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

// Title rules validators
const titleRules = [(val: string | null) => !!val?.trim() || 'Name is required']
</script>
