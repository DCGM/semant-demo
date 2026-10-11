<template>
  <!-- Collapses/expands a drawer to its mini state. It is neutral and double-chevroned on
       purpose so it is not mistaken for a blue back arrow (#253); it never navigates. -->
  <q-btn
    size="15px"
    dense
    round
    unelevated
    class="mini-state-btn"
    :icon="icon"
    :aria-label="label"
    :aria-expanded="!drawerMiniState"
    @click="emit('click')"
  >
    <q-tooltip>{{ label }}</q-tooltip>
  </q-btn>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  drawerMiniState: boolean;
  side?: 'left' | 'right';
}>(), { side: 'left' })

const emit = defineEmits(['click'])

// points in the direction the drawer will move
const icon = computed(() => {
  const expand = props.side === 'left' ? 'keyboard_double_arrow_right' : 'keyboard_double_arrow_left'
  const collapse = props.side === 'left' ? 'keyboard_double_arrow_left' : 'keyboard_double_arrow_right'
  return props.drawerMiniState ? expand : collapse
})

const label = computed(() => {
  const target = props.side === 'left' ? 'navigation' : 'sidebar'
  return props.drawerMiniState ? `Expand ${target}` : `Collapse ${target}`
})
</script>

<style scoped lang="scss">
.mini-state-btn {
  background: #fff;
  color: #5f6368;
  border: 1px solid rgba(0, 0, 0, 0.12);
}
</style>
