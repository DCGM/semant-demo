<template>
  <!-- The shell of the create/edit form dialogs (#479). Quasar sends Escape and backdrop clicks
       to the topmost overlay only and, with no-esc-dismiss/no-backdrop-dismiss, reports them as
       a shake: that closes the form, or asks first when it has changes. The shake animation
       itself is turned off below. -->
  <q-dialog
    ref="dialog"
    class="form-dialog"
    no-esc-dismiss
    no-backdrop-dismiss
    @shake="requestClose"
    @hide="emit('hide')"
  >
    <q-card ref="card" class="q-pa-sm" style="width: 900px">
      <slot />
      <q-card-actions align="right">
        <q-btn flat label="Cancel" color="primary" :disable="props.busy" @click="requestClose" />
        <q-btn unelevated color="primary" :label="props.okLabel" :loading="props.busy" @click="emit('confirm')" />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { QCard, QDialog, useQuasar } from 'quasar'

const props = defineProps<{
  /** Whether the form has changes that closing would discard. */
  dirty: boolean
  okLabel: string
  /** A save is under way: the form stays open and cannot be closed or sent again. */
  busy?: boolean
}>()

// confirm: the OK button; the form validates and closes the dialog itself.
const emit = defineEmits<{ hide: [], confirm: [] }>()

const $q = useQuasar()
const dialog = ref<QDialog | null>(null)
const card = ref<QCard | null>(null)

const show = () => dialog.value?.show()
const hide = () => dialog.value?.hide()

/** Closes at once when nothing was changed, otherwise asks before discarding (Cancel, Escape, outside click). */
const requestClose = () => {
  if (props.busy) return
  if (!props.dirty) {
    hide()
    return
  }
  $q.dialog({
    title: 'Unsaved Changes',
    message: 'You have unsaved changes. Are you sure you want to discard them?',
    ok: 'Yes',
    cancel: 'No',
    // The click that opened it (e.g. on Cancel) must not count as a click outside.
    noBackdropDismiss: true
  }).onOk(hide)
}

// Quasar's clear (✕) and other in-field actions are left out of the Tab order, so Tab goes
// from field to field. They appear with the field's value, so added nodes are checked too.
const FIELD_ACTION = '.q-field__focusable-action'
const skipFieldActions = (node: Node) => {
  if (!(node instanceof Element)) return
  if (node.matches(FIELD_ACTION)) node.setAttribute('tabindex', '-1')
  node.querySelectorAll(FIELD_ACTION).forEach((el) => el.setAttribute('tabindex', '-1'))
}
let observer: MutationObserver | null = null
watch(() => card.value?.$el as Element | undefined, (root) => {
  observer?.disconnect()
  observer = null
  if (!(root instanceof Element)) return
  skipFieldActions(root)
  observer = new MutationObserver((mutations) => mutations.forEach((m) => m.addedNodes.forEach(skipFieldActions)))
  observer.observe(root, { childList: true, subtree: true })
}, { immediate: true, flush: 'post' })
onBeforeUnmount(() => observer?.disconnect())

// For useDialogPluginComponent, whose dialogRef this component is.
defineExpose({ show, hide })
</script>

<style lang="scss">
.form-dialog .q-dialog__inner.q-animate--scale {
  animation: none;
}
</style>
