<template>
  <div
    class="boundary-editor"
    role="group"
    aria-label="Edit the annotation's boundaries"
    data-testid="boundary-editor"
    @keydown.esc.stop="emit('cancel')"
  >
    <div class="boundary-editor__hint text-caption">
      Move the start or the end, or select text in the passage below and use it.
      The new range is marked in blue.
    </div>
    <div class="boundary-editor__steps">
      <div v-for="handle in HANDLES" :key="handle" class="boundary-editor__handle" role="group" :aria-label="LABEL[handle]">
        <span class="boundary-editor__label">{{ LABEL[handle] }}</span>
        <q-btn
          dense
          outline
          no-caps
          color="primary"
          icon="chevron_left"
          :aria-label="`Move the ${handle} one ${unit} earlier`"
          :disable="saving"
          :data-testid="`boundary-${handle}-earlier`"
          @click="emit('step', handle, -1)"
        />
        <q-btn
          dense
          outline
          no-caps
          color="primary"
          icon="chevron_right"
          :aria-label="`Move the ${handle} one ${unit} later`"
          :disable="saving"
          :data-testid="`boundary-${handle}-later`"
          @click="emit('step', handle, 1)"
        />
      </div>
      <q-btn-toggle
        :model-value="unit"
        dense
        no-caps
        unelevated
        toggle-color="primary"
        color="grey-3"
        text-color="grey-9"
        aria-label="Step by"
        :options="[{ label: 'Word', value: 'word' }, { label: 'Character', value: 'character' }]"
        data-testid="boundary-unit"
        @update:model-value="value => emit('update:unit', value)"
      />
    </div>
    <q-btn
      dense
      flat
      no-caps
      color="primary"
      icon="highlight_alt"
      label="Use selected text"
      class="boundary-editor__use-selection"
      :disable="saving"
      data-testid="boundary-use-selection"
      @mousedown.prevent
      @click="emit('use-selection')"
    />
    <blockquote class="boundary-editor__preview text-body2" aria-live="polite" data-testid="boundary-preview">
      {{ text || '…' }}
    </blockquote>
    <div v-if="note" class="boundary-editor__note text-caption" role="status" data-testid="boundary-note">{{ note }}</div>
    <div class="boundary-editor__actions">
      <q-btn
        dense
        unelevated
        no-caps
        color="primary"
        icon="save"
        label="Save boundaries"
        :disable="!changed"
        :loading="saving"
        data-testid="boundary-save"
        @click="emit('save')"
      />
      <q-btn dense flat no-caps color="primary" label="Cancel" :disable="saving" data-testid="boundary-cancel" @click="emit('cancel')" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { QBtn, QBtnToggle } from 'quasar'
import type { BoundaryHandle, BoundaryUnit } from './boundaryEdit'

defineProps<{
  /** The text of the range being edited. */
  text: string
  unit: BoundaryUnit
  /** The range differs from the saved one. */
  changed: boolean
  saving: boolean
  /** Why the last step or selection was not applied. */
  note: string | null
}>()

const emit = defineEmits<{
  step: [handle: BoundaryHandle, direction: -1 | 1]
  'update:unit': [unit: BoundaryUnit]
  'use-selection': []
  save: []
  cancel: []
}>()

const HANDLES: BoundaryHandle[] = ['start', 'end']
const LABEL: Record<BoundaryHandle, string> = { start: 'Start', end: 'End' }
</script>

<style scoped>
.boundary-editor {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 6px 0;
  padding: 6px 8px;
  border-left: 3px solid #0277bd;
  background: rgba(2, 119, 189, 0.06);
}

.boundary-editor__hint {
  color: rgba(0, 0, 0, 0.7);
}

.boundary-editor__steps,
.boundary-editor__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 12px;
}

.boundary-editor__handle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.boundary-editor__label {
  min-width: 2.5em;
  font-size: 0.85rem;
}

.boundary-editor__use-selection {
  align-self: flex-start;
}

.boundary-editor__preview {
  margin: 0;
  padding: 4px 8px;
  background: #e1f5fe;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 7em;
  overflow-y: auto;
}

.boundary-editor__note {
  color: #8a5300;
}
</style>
