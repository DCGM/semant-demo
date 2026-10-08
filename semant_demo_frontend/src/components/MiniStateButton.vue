<template>
  <q-btn
    size="15px"
    dense
    round
    unelevated
    color="primary"
    :icon="icon"
    @click="miniStateClick"
  />
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
  const expand = props.side === 'left' ? 'chevron_right' : 'chevron_left'
  const collapse = props.side === 'left' ? 'chevron_left' : 'chevron_right'
  return props.drawerMiniState ? expand : collapse
})

const miniStateClick = () => {
  console.log('Mini state clicked')
  emit('click')
}

</script>
