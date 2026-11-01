<template>
  <!-- The values of one attribute on one annotation (#331): checking or unchecking a value is
       one assignment, saved at once. A single-valued attribute shows radio buttons, a
       multi-valued one checkboxes; retired values show only while held, to be removed. -->
  <q-list dense class="attribute-value-picker" role="group" :aria-label="`Values of ${attribute.name}`" data-testid="attribute-value-picker">
    <q-item-label header class="attribute-value-picker__header">
      {{ attribute.name }}
      <q-spinner v-if="busy" size="1em" color="primary" class="q-ml-xs" aria-label="Saving" />
    </q-item-label>
    <q-item
      v-for="value in offered"
      :key="value.id"
      tag="label"
      :disable="busy"
      :data-testid="`attribute-pick-${value.id}`"
    >
      <q-item-section side>
        <q-radio
          v-if="single"
          dense
          :model-value="held.has(value.id) ? value.id : null"
          :val="value.id"
          :disable="busy"
          @update:model-value="pick(value, true)"
        />
        <q-checkbox
          v-else
          dense
          :model-value="held.has(value.id)"
          :disable="busy"
          @update:model-value="(checked: boolean) => pick(value, checked)"
        />
      </q-item-section>
      <q-item-section>
        <q-item-label :class="{ 'attribute-value-picker__special': isSpecial(value) }">
          {{ valueName(value) }}
          <span v-if="value.retired" class="text-grey-7">(retired)</span>
        </q-item-label>
      </q-item-section>
    </q-item>
    <q-item v-for="id in unknownIds" :key="id" dense>
      <q-item-section class="text-italic text-grey-8">Unknown value (no longer defined)</q-item-section>
    </q-item>
    <q-item v-if="!offered.length" dense>
      <q-item-section class="text-grey-7">This attribute has no values yet.</q-item-section>
    </q-item>
    <q-separator v-if="current.length" spaced />
    <q-item
      v-if="current.length"
      clickable
      :disable="busy"
      data-testid="attribute-pick-clear"
      @click="emit('change', clearChange())"
    >
      <q-item-section side><q-icon name="backspace" size="xs" /></q-item-section>
      <q-item-section>Clear ({{ current.length }})</q-item-section>
    </q-item>
  </q-list>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { QCheckbox, QIcon, QItem, QItemLabel, QItemSection, QList, QRadio, QSeparator, QSpinner } from 'quasar'
import { Cardinality, type Attribute, type AttributeValue } from 'src/generated/api'
import { isSpecial, valueName } from './attributeForm'
import { clearChange, offeredValues, pickChange, type AssignChange } from './assignment'

const props = defineProps<{
  attribute: Attribute
  /** The value ids the annotation holds of the attribute. */
  current: string[]
  /** An assignment of the annotation is under way. */
  busy?: boolean
}>()

const emit = defineEmits<{ change: [change: AssignChange] }>()

const single = computed(() => props.attribute.cardinality === Cardinality.single)
const held = computed(() => new Set(props.current))
const offered = computed(() => offeredValues(props.attribute, props.current))
const unknownIds = computed(() => {
  const known = new Set((props.attribute.values ?? []).map(v => v.id))
  return props.current.filter(id => !known.has(id))
})

function pick (value: AttributeValue, checked: boolean) {
  if (props.busy || held.value.has(value.id) === checked) return
  emit('change', pickChange(props.attribute, props.current, value, checked))
}
</script>

<style scoped>
.attribute-value-picker {
  min-width: 220px;
  max-height: 360px;
  overflow-y: auto;
}

.attribute-value-picker__header {
  display: flex;
  align-items: center;
  padding-top: 8px;
  padding-bottom: 4px;
  font-weight: 600;
  color: rgba(0, 0, 0, 0.75);
}

.attribute-value-picker__special {
  font-style: italic;
}
</style>
