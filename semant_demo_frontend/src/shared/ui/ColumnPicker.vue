<template>
  <!-- Toggles which optional columns a q-table shows (bind to its visible-columns). -->
  <q-select
    :model-value="props.modelValue"
    multiple
    outlined
    options-dense
    dense
    :display-value="$q.lang.table.columns"
    :options="options"
    option-value="name"
    emit-value
    style="min-width: 150px"
    transition-hide="scale"
    transition-show="scale"
    color="primary"
    class="text-grey-2"
    @update:model-value="(value: string[]) => emit('update:modelValue', value)"
  >
    <template #option="{ itemProps, opt, selected, toggleOption }">
      <q-item v-bind="itemProps">
        <q-item-section>
          <q-item-label>{{ opt.label }}</q-item-label>
        </q-item-section>
        <q-item-section side>
          <q-toggle
            :model-value="selected"
            @update:model-value="toggleOption(opt)"
          />
        </q-item-section>
      </q-item>
    </template>
  </q-select>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  /** Names of the visible columns. */
  modelValue: string[]
  /** The table's columns; the required ones cannot be hidden and are not offered. */
  columns: { name: string, label: string, required?: boolean }[]
}>()

const options = computed(() => props.columns.filter((column) => !column.required))

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
}>()
</script>
