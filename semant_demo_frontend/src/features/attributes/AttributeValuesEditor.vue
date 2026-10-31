<template>
  <!-- The values of an existing attribute in its Edit dialog (#506). Each change is its own
       write and is saved at once; the dialog's Save only sends the attribute's own fields. -->
  <div class="attribute-values-editor" data-testid="attribute-values-editor">
    <div class="text-subtitle1">Values ({{ ordinary.length }})</div>
    <div class="text-caption text-grey-8 q-mb-sm" data-testid="attribute-values-immediate">
      Changes to values are saved immediately. Save and Cancel below apply only to the fields
      above; Cancel does not undo value changes.
    </div>

    <div class="column q-mb-sm">
      <q-checkbox
        v-for="kind in SPECIAL_KINDS"
        :key="kind"
        dense
        class="q-py-xs"
        :model-value="allows(props.attribute, kind)"
        :label="`Allow ${KIND_LABELS[kind]}`"
        :disable="locked"
        :data-testid="`attribute-allow-${kind}`"
        @update:model-value="(allowed: boolean) => setSpecial(kind, allowed)"
      />
      <div class="text-caption text-grey-7">
        Explicit decisions, distinct from no value. Withdrawing one keeps the annotations that have it.
      </div>
    </div>

    <div class="row items-center q-col-gutter-sm q-mb-sm">
      <div class="col">
        <q-input
          v-model="filter"
          dense
          outlined
          clearable
          debounce="150"
          placeholder="Search values"
          aria-label="Search values"
          :disable="!ordinary.length"
        >
          <template #prepend>
            <q-icon name="search" />
          </template>
        </q-input>
      </div>
      <div class="col-auto">
        <q-btn
          flat
          no-caps
          color="primary"
          icon="add"
          label="Add value"
          :disable="locked || (props.attribute.values ?? []).length >= MAX_VALUES"
          @click="addValue"
        />
      </div>
    </div>

    <q-list bordered separator dense class="attribute-values-editor__list rounded-borders">
      <q-item
        v-for="value in listed"
        :key="value.id"
        :class="{ 'attribute-values-editor__retired': value.retired }"
        data-testid="attribute-dialog-value-row"
      >
        <q-item-section>
          <q-item-label class="attribute-values-editor__label">
            <HighlightedText :text="value.label" :needle="filter" data-testid="attribute-dialog-value-label" />
            <q-badge v-if="value.retired" color="grey-7" class="q-ml-sm" label="Retired" />
          </q-item-label>
          <q-item-label v-if="value.description || value.examples?.length" caption lines="1">
            {{ value.description }}<template v-if="value.description && value.examples?.length"> · </template>
            <template v-if="value.examples?.length">e.g. {{ value.examples.join('; ') }}</template>
          </q-item-label>
        </q-item-section>
        <q-item-section side>
          <div class="row no-wrap">
            <q-btn
              flat
              round
              dense
              size="sm"
              color="primary"
              icon="edit"
              :disable="locked"
              :aria-label="`Edit ${value.label}`"
              @click="editValue(value)"
            />
            <q-btn
              flat
              round
              dense
              size="sm"
              color="grey-8"
              :icon="value.retired ? 'unarchive' : 'archive'"
              :loading="pending === value.id"
              :disable="locked"
              :aria-label="`${value.retired ? 'Restore' : 'Retire'} ${value.label}`"
              @click="setRetired(value, !value.retired)"
            >
              <q-tooltip>{{ value.retired ? 'Restore: can be assigned again' : 'Retire: annotations keep it, but it is not assigned again' }}</q-tooltip>
            </q-btn>
          </div>
        </q-item-section>
      </q-item>
      <q-item v-if="!listed.length">
        <q-item-section class="text-grey-7" data-testid="attribute-dialog-values-empty">
          {{ ordinary.length ? 'No values match.' : 'No values yet.' }}
        </q-item-section>
      </q-item>
    </q-list>
    <div v-if="filter && ordinary.length" class="text-caption text-grey-7 q-mt-xs">
      {{ listed.length }} of {{ ordinary.length }} values match.
    </div>

    <q-banner v-if="error" dense rounded class="bg-red-1 text-negative q-mt-sm" role="alert" data-testid="attribute-values-error">
      {{ error }}
    </q-banner>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useQuasar } from 'quasar'

import type { Attribute, AttributeValue, PatchAttributeValue, PostAttributeValue } from 'src/generated/api'
import { successNotification } from 'src/shared/notification'
import { KIND_LABELS, MAX_VALUES, SPECIAL_KINDS, allows, isSpecial, type SpecialKind, type ValueActions } from './attributeForm'
import { matches } from './attributeSearch'
import AttributeValueDialog from './AttributeValueDialog.vue'
import HighlightedText from './HighlightedText.vue'

const props = defineProps<{
  /** The attribute as last saved. */
  attribute: Attribute
  actions: ValueActions
  /** Another save of the dialog is running: nothing here can be changed meanwhile. */
  disabled?: boolean
}>()

const emit = defineEmits<{
  /** A write saved: the attribute it answered with. */
  saved: [attribute: Attribute]
  /** Whether a write of this section is running. */
  busy: [busy: boolean]
}>()

const $q = useQuasar()
const filter = ref<string | null>('')
// The value (or `special:<kind>`) whose write is running; one at a time.
const pending = ref<string | null>(null)
const error = ref<string | null>(null)
const locked = computed(() => props.disabled || pending.value !== null)
watch(pending, value => emit('busy', value !== null))

const ordinary = computed(() => (props.attribute.values ?? []).filter(v => !isSpecial(v)))
const listed = computed(() => filter.value?.trim() ? ordinary.value.filter(v => matches(v.label, filter.value)) : ordinary.value)

/** Runs one write; its answer is the attribute as saved, a failure stays shown here. */
async function run (key: string, write: () => Promise<Attribute>, done: string) {
  if (locked.value) return
  pending.value = key
  error.value = null
  try {
    emit('saved', await write())
    successNotification(done)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'The change could not be saved.'
  } finally {
    pending.value = null
  }
}

function setSpecial (kind: SpecialKind, allowed: boolean) {
  void run(`special:${kind}`, () => props.actions.setSpecialValue(props.attribute, kind, allowed),
    `${KIND_LABELS[kind]} ${allowed ? 'allowed' : 'withdrawn'}`)
}

function setRetired (value: AttributeValue, retired: boolean) {
  void run(value.id, () => props.actions.updateValue(value.id, { retired }),
    `"${value.label}" ${retired ? 'retired' : 'restored'}`)
}

/** Opens the value dialog; it saves on its own and stays open on a failure. */
type SaveValue = ((body: PostAttributeValue) => Promise<Attribute>) | ((patch: PatchAttributeValue) => Promise<Attribute>)

function openValueDialog (value: AttributeValue | undefined, save: SaveValue, done: string) {
  if (locked.value) return
  error.value = null
  $q.dialog({
    component: AttributeValueDialog,
    componentProps: { attributeName: props.attribute.name, value, save }
  }).onOk((saved: Attribute | null) => {
    if (!saved) return
    emit('saved', saved)
    successNotification(done)
  })
}

function addValue () {
  openValueDialog(undefined, (body: PostAttributeValue) => props.actions.addValue(body), 'Value added')
}

function editValue (value: AttributeValue) {
  openValueDialog(value, (patch: PatchAttributeValue) => props.actions.updateValue(value.id, patch), 'Value saved')
}
</script>

<style scoped>
.attribute-values-editor__list {
  max-height: 320px;
  overflow-y: auto;
}

.attribute-values-editor__label {
  overflow-wrap: anywhere;
}

.attribute-values-editor__retired [data-testid='attribute-dialog-value-label'] {
  color: rgba(0, 0, 0, 0.5);
  text-decoration: line-through;
}
</style>
