<template>
  <q-btn
    v-bind="$attrs"
    class="q-my-sm q-mr-sm q-px-md"
    unelevated
    no-wrap
    :color="props.color"
    :icon="props.icon"
    no-caps
    :label="props.label"
  />
</template>

<script setup lang="ts">
interface Props {
  color?: string
  icon?: string
  label: string
}

const props = withDefaults(defineProps<Props>(), {
  label: 'Button'
})
</script>
