<template>
  <!-- Assigns one attribute's values to the selected annotations (#331): the attribute, what to
       do with its values and which values, with the target count and what will happen. The
       dialog runs the assignment and closes once it is done; the per-annotation result is then
       shown above the list. While it runs nothing that goes into it can change. -->
  <FormDialog
    ref="dialogRef"
    :dirty="!!attributeId"
    :busy="saving"
    :ok-label="okLabel"
    @hide="onDialogHide"
    @confirm="submit"
  >
    <q-card-section>
      <div class="text-h5 text-grey-9">Assign attribute</div>
      <div class="text-body2 text-grey-8" data-testid="assign-target">
        To {{ plural(props.count, 'selected annotation') }}<template v-if="props.offPage">,
          {{ props.offPage }} of them not on this page</template>.
      </div>
    </q-card-section>

    <q-card-section class="q-gutter-y-md">
      <div v-if="!props.attributes.length" class="text-body2 text-grey-8" data-testid="assign-no-attributes">
        This collection has no attributes yet. Define them in the Attributes part of the Tags &amp; attributes tab.
      </div>
      <template v-else>
        <q-select
          v-model="attributeId"
          :options="attributeOptions"
          emit-value
          map-options
          outlined
          options-dense
          label="Attribute"
          :disable="saving"
          data-testid="assign-dialog-attribute"
        />

        <template v-if="attribute">
          <div>
            <div class="text-caption text-grey-8 q-mb-xs" id="assign-mode-label">What to do</div>
            <q-btn-toggle
              v-model="mode"
              :options="modeOptions"
              no-caps
              unelevated
              toggle-color="primary"
              color="grey-2"
              text-color="grey-9"
              :disable="saving"
              aria-labelledby="assign-mode-label"
              data-testid="assign-mode"
            />
            <div class="text-caption text-grey-7 q-mt-xs">{{ modeHint }}</div>
          </div>

          <div v-if="mode !== 'clear'" data-testid="assign-values">
            <div class="text-caption text-grey-8 q-mb-xs">
              {{ mode === 'remove' ? 'Values to remove' : single ? 'Value' : 'Values' }}
            </div>
            <q-input
              v-if="choices.length > 8"
              v-model="filter"
              dense
              outlined
              clearable
              placeholder="Search values"
              aria-label="Search values"
              class="q-mb-xs"
              :disable="saving"
            />
            <div class="assign-dialog__values">
              <q-option-group
                v-if="single && mode === 'set'"
                v-model="singleValue"
                :options="filteredChoices"
                type="radio"
                dense
                :disable="saving"
              />
              <q-option-group
                v-else
                :model-value="valueIds"
                :options="filteredChoices"
                type="checkbox"
                dense
                :disable="saving"
                @update:model-value="chooseValues"
              />
              <div v-if="!choices.length" class="text-caption text-grey-7">This attribute has no values to choose.</div>
            </div>
          </div>

          <div class="assign-dialog__summary text-body2" role="status" data-testid="assign-summary">
            <div>{{ summary }}</div>
            <div class="text-caption text-grey-8 q-mt-xs">
              Only confirmed annotations with a tag this attribute applies to ({{ scopeText }}) take values; the
              others are reported as not changed. Annotations someone else changed meanwhile are not overwritten.
            </div>
          </div>
        </template>
      </template>

      <div v-if="saving" class="row items-center q-gutter-x-sm text-body2" role="status" aria-live="polite">
        <q-spinner color="primary" size="1.2em" />
        <span>Saving {{ props.progress?.() ?? 0 }} / {{ props.count }}…</span>
      </div>
      <q-banner v-if="error" dense rounded class="bg-red-1 text-negative" role="alert" data-testid="assign-error">
        {{ error }}
      </q-banner>
    </q-card-section>
  </FormDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { QBanner, QBtnToggle, QCardSection, QInput, QOptionGroup, QSelect, QSpinner, useDialogPluginComponent } from 'quasar'
import FormDialog from 'src/shared/ui/FormDialog.vue'
import { plural } from 'src/shared/plural'
import { AssignMode, Cardinality, type Attribute, type Tag } from 'src/generated/api'
import { isSpecial, orderedValues, tagScope, valueName } from './attributeForm'
import { quotedValues, type AssignChange } from './assignment'
import type { AssignReport } from './attributeAssignStore'

type Mode = 'add' | 'remove' | 'replace' | 'set' | 'clear'
type Save = (attributeId: string, change: AssignChange) => Promise<AssignReport | null>
type Progress = () => number

const props = defineProps<{
  /** The attributes values can be assigned of (not retired). */
  attributes: Attribute[]
  tags: Tag[]
  /** Selected annotations the assignment targets. */
  count: number
  /** How many of them are not on the current page. */
  offPage?: number
  /** Runs the assignment; null when the workspace was left meanwhile. */
  save: Save
  /** Annotations sent so far, while it runs. */
  progress?: Progress
}>()

defineEmits([...useDialogPluginComponent.emits])
const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()

const attributeId = ref<string | null>(props.attributes.length === 1 ? props.attributes[0]!.id : null)
const attribute = computed(() => props.attributes.find(a => a.id === attributeId.value) ?? null)
const single = computed(() => attribute.value?.cardinality === Cardinality.single)
const mode = ref<Mode>(single.value ? 'set' : 'add')
const valueIds = ref<string[]>([])
const singleValue = ref<string | null>(null)
const filter = ref('')
const saving = ref(false)
const error = ref<string | null>(null)

const attributeOptions = computed(() => props.attributes.map(a => ({
  label: `${a.name} (${a.cardinality === Cardinality.single ? 'one value' : 'several values'})`,
  value: a.id
})))

const modeOptions = computed(() => single.value
  ? [{ label: 'Set', value: 'set' }, { label: 'Clear', value: 'clear' }]
  : [{ label: 'Add', value: 'add' }, { label: 'Remove', value: 'remove' }, { label: 'Replace', value: 'replace' }])

const hasSpecial = computed(() => (attribute.value?.values ?? []).some(v => isSpecial(v) && !v.retired))
const modeHint = computed(() => ({
  add: 'Adds the values; the values the annotations already have stay.' + (hasSpecial.value
    ? ' Annotations marked Unknown or Not applicable keep that and are reported as not changed; use Replace to change them.'
    : ''),
  remove: 'Removes the values from the annotations that have them.',
  replace: 'The annotations get exactly these values; their other values of this attribute are removed.',
  set: 'The annotations get this value instead of the one they have.',
  clear: 'Removes the value of this attribute from the annotations.'
})[mode.value])

watch(attributeId, () => {
  mode.value = single.value ? 'set' : 'add'
  valueIds.value = []
  singleValue.value = null
  filter.value = ''
  error.value = null
})
watch(mode, () => {
  valueIds.value = []
  singleValue.value = null
})

/** The values offered: retired ones only to remove them. */
const choices = computed(() => {
  const a = attribute.value
  if (!a) return []
  return orderedValues(a)
    .filter(v => mode.value === 'remove' || !v.retired)
    .map(v => ({ label: v.retired ? `${valueName(v)} (retired)` : valueName(v), value: v.id, special: isSpecial(v) }))
})
const filteredChoices = computed(() => {
  const needle = (filter.value ?? '').trim().toLowerCase()
  const chosen = new Set(single.value ? [singleValue.value] : valueIds.value)
  return needle ? choices.value.filter(c => chosen.has(c.value) || c.label.toLowerCase().includes(needle)) : choices.value
})

/** Unknown and Not applicable stand alone (ADR 0011): choosing one drops the others, choosing an
 * ordinary value drops them; removing may name any. */
function chooseValues (next: string[]) {
  if (mode.value === 'remove') {
    valueIds.value = next
    return
  }
  const special = new Set(choices.value.filter(c => c.special).map(c => c.value))
  const added = next.find(id => !valueIds.value.includes(id))
  if (added && special.has(added)) valueIds.value = [added]
  else valueIds.value = next.filter(id => !special.has(id))
}

const change = computed<AssignChange | null>(() => {
  const a = attribute.value
  if (!a) return null
  if (mode.value === 'clear') return { mode: AssignMode.remove, valueIds: (a.values ?? []).map(v => v.id) }
  if (mode.value === 'set') return singleValue.value ? { mode: AssignMode.replace, valueIds: [singleValue.value] } : null
  return valueIds.value.length ? { mode: mode.value, valueIds: [...valueIds.value] } : null
})

const VERB: Record<Mode, string> = { add: 'Add to', remove: 'Remove from', replace: 'Replace on', set: 'Set on', clear: 'Clear on' }
const okLabel = computed(() => `${VERB[mode.value]} ${props.count}`)

const summary = computed(() => {
  const a = attribute.value
  if (!a) return ''
  const n = plural(props.count, 'annotation')
  const values = quotedValues(a, mode.value === 'set' ? (singleValue.value ? [singleValue.value] : []) : valueIds.value)
  if (mode.value === 'clear') return `Remove every value of "${a.name}" from ${n}.`
  if (!values) return mode.value === 'set' ? 'Choose the value.' : 'Choose the values.'
  return {
    add: `Add ${values} to "${a.name}" of ${n}.`,
    remove: `Remove ${values} from "${a.name}" of ${n}.`,
    replace: `Set "${a.name}" of ${n} to exactly ${values}.`,
    set: `Set "${a.name}" of ${n} to ${values}.`
  }[mode.value]
})

const scopeText = computed(() => {
  const a = attribute.value
  if (!a) return ''
  const scope = tagScope(a, props.tags, 'ready')
  if (scope.kind === 'all') return 'all tags'
  if (scope.kind === 'selected' && scope.names.length) return scope.names.join(', ')
  return 'no tag'
})

async function submit () {
  const a = attribute.value
  const c = change.value
  if (saving.value) return
  if (!a || !c) {
    error.value = !a ? 'Choose an attribute.' : mode.value === 'set' ? 'Choose a value.' : 'Choose at least one value.'
    return
  }
  saving.value = true
  error.value = null
  try {
    const report = await props.save(a.id, c)
    if (!report) {
      onDialogCancel()
      return
    }
    // Refused as a whole (nothing saved): stay open with the reason and the choices.
    if (report.error && !report.saved.length && !report.conflicts.length && !report.refused.length) {
      error.value = report.error
      return
    }
    onDialogOK(report)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.assign-dialog__values {
  max-height: 16rem;
  overflow-y: auto;
}

.assign-dialog__summary {
  padding: 6px 10px;
  border-left: 3px solid var(--q-primary);
  background: rgba(25, 118, 210, 0.06);
}
</style>
